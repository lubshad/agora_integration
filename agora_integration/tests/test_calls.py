import base64
import hashlib
import hmac
import struct
import unittest
import zlib
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.utils import add_to_date, now_datetime

from agora_integration.services import calls
from agora_integration.services.tokens import build_rtc_token


class TokenTests(unittest.TestCase):
	def test_access_token2_signature_and_binding(self) -> None:
		app_id, certificate = "a" * 32, "b" * 32
		token = build_rtc_token(app_id, certificate, "call_test", 17, 600, issue_time=1000, salt=123)
		self.assertTrue(token.startswith("007"))
		decoded = zlib.decompress(base64.b64decode(token[3:]))
		self.assertEqual(struct.unpack("<H", decoded[:2])[0], 32)
		signature, info = decoded[2:34], decoded[34:]
		key = hmac.new(struct.pack("<I", 1000), certificate.encode(), hashlib.sha256).digest()
		key = hmac.new(struct.pack("<I", 123), key, hashlib.sha256).digest()
		self.assertEqual(signature, hmac.new(key, info, hashlib.sha256).digest())
		self.assertIn(b"call_test", info)
		self.assertTrue(info.endswith(b"\x02\x0017"))

	def test_invalid_token_parameters(self) -> None:
		for uid, ttl, channel in ((0, 600, "ok"), (1, 0, "ok"), (1, 600, "invalid/channel")):
			with self.assertRaises(ValueError):
				build_rtc_token("a" * 32, "b" * 32, channel, uid, ttl)


@unittest.skipUnless(getattr(frappe.local, "site", None), "Requires connected local site")
class CallLifecycleTests(unittest.TestCase):
	def setUp(self) -> None:
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.patchers = [
			patch("frappe.enqueue"),
			patch.object(calls, "notify"),
			patch.object(
				calls, "get_settings", return_value=SimpleNamespace(ring_timeout=45, connect_timeout=45)
			),
			patch.object(calls, "_device", side_effect=lambda: self.devices[frappe.session.user]),
		]
		for patcher in self.patchers:
			patcher.start()
		self.users = []
		self.devices = {}
		for index in range(3):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": f"call-{uuid4().hex}@example.invalid",
					"first_name": f"Call Test {index}",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			self.users.append(user.name)
			device = frappe.get_doc(
				{
					"doctype": "Flutter Device Credential",
					"user": user.name,
					"device_id_hash": uuid4().hex,
					"device_key": uuid4().hex,
					"api_key": uuid4().hex,
					"api_secret": uuid4().hex,
					"enabled": 1,
					"last_login_at": now_datetime(),
				}
			).insert(ignore_permissions=True)
			self.devices[user.name] = device.name
		frappe.set_user(self.users[0])

	def tearDown(self) -> None:
		frappe.db.rollback()
		frappe.set_user(self.previous_user)
		for patcher in reversed(self.patchers):
			patcher.stop()

	def start(self, request: str | None = None) -> dict:
		return calls.start_call(
			"test_calls", self.users[1], "audio", request or str(uuid4()), lambda call, action: None
		)

	def test_idempotent_start_and_busy_protection(self) -> None:
		request = str(uuid4())
		first = self.start(request)
		self.assertEqual(first["id"], self.start(request)["id"])
		with self.assertRaises(frappe.ValidationError):
			self.start()

	def test_accept_connect_and_end(self) -> None:
		call = self.start()
		frappe.set_user(self.users[1])
		accepted = calls.act(call["id"], "test_calls", "accept", lambda call, action: None)
		self.assertEqual(accepted["state"], "Connecting")
		calls.report_connection(call["id"], "test_calls", True, lambda call, action: None)
		frappe.set_user(self.users[0])
		connected = calls.report_connection(call["id"], "test_calls", True, lambda call, action: None)
		self.assertEqual(connected["state"], "Active")
		ended = calls.act(call["id"], "test_calls", "end", lambda call, action: None)
		self.assertEqual(ended["state"], "Ended")
		self.assertTrue(ended["unpaid"])
		self.assertIsNone(calls.get_active_call("test_calls"))

	def test_other_user_and_project_denied(self) -> None:
		call = self.start()
		with self.assertRaises(frappe.PermissionError):
			calls.get_call(call["id"], "another_project")
		frappe.set_user(self.users[2])
		with self.assertRaises(frappe.PermissionError):
			calls.get_call(call["id"], "test_calls")
		self.assertEqual(calls.list_call_history("test_calls"), [])

	def test_caller_cannot_accept_or_decline(self) -> None:
		call = self.start()
		for action in ("accept", "decline"):
			with self.assertRaises(frappe.PermissionError):
				calls.act(call["id"], "test_calls", action, lambda call, action: None)

	def test_accept_claim_is_device_bound(self) -> None:
		call = self.start()
		frappe.set_user(self.users[1])
		calls.act(call["id"], "test_calls", "accept", lambda call, action: None)
		with patch.object(calls, "_device", return_value="another-device"):
			with self.assertRaises(frappe.PermissionError):
				calls.act(call["id"], "test_calls", "accept", lambda call, action: None)
			with self.assertRaises(frappe.PermissionError):
				calls.renew_call_token(call["id"], "test_calls", lambda call, action: None)

	def test_expired_invitation_cannot_be_accepted(self) -> None:
		call = self.start()
		frappe.db.set_value(
			"Agora Call Session", call["id"], "deadline", add_to_date(now_datetime(), seconds=-1)
		)
		frappe.set_user(self.users[1])
		result = calls.act(call["id"], "test_calls", "accept", lambda call, action: None)
		self.assertEqual(result["state"], "Timed Out")

	def test_ringing_and_terminal_calls_cannot_issue_token(self) -> None:
		call = self.start()
		with self.assertRaises(frappe.ValidationError):
			calls.renew_call_token(call["id"], "test_calls", lambda call, action: None)
		calls.act(call["id"], "test_calls", "cancel", lambda call, action: None)
		with self.assertRaises(frappe.ValidationError):
			calls.renew_call_token(call["id"], "test_calls", lambda call, action: None)

	def test_policy_denial_creates_no_session(self) -> None:
		def deny(call: object, action: str) -> None:
			raise frappe.PermissionError

		with self.assertRaises(frappe.PermissionError):
			calls.start_call("test_calls", self.users[1], "audio", str(uuid4()), deny)
		self.assertIsNone(calls.get_active_call("test_calls"))

	def test_standard_crud_permissions_are_denied(self) -> None:
		for doctype in ("Agora Call Session", "Agora Call Event", "Agora Settings"):
			for permission in ("read", "write", "create"):
				self.assertFalse(frappe.has_permission(doctype, permission, user=self.users[0]))
