import hashlib
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from agora_integration.services import voip_devices as devices


class VoipDeviceTests(TestCase):
	def setUp(self) -> None:
		self.frappe_patch = patch.object(devices, "frappe")
		self.frappe = self.frappe_patch.start()
		self.addCleanup(self.frappe_patch.stop)
		translation = patch.object(devices, "_", side_effect=lambda value: value)
		translation.start()
		self.addCleanup(translation.stop)
		self.frappe.AuthenticationError = frappe.AuthenticationError
		self.frappe.session.user = "user@test"
		self.frappe.throw.side_effect = frappe.ValidationError
		self.device_patch = patch.object(devices, "get_current_device_credential", return_value="DEV-1")
		self.current = self.device_patch.start()
		self.addCleanup(self.device_patch.stop)
		self.frappe.db.exists.return_value = False

	def test_register_uses_current_device_and_preserves_response(self) -> None:
		with patch.object(devices, "save_registration") as save:
			result = devices.register_voip_device(" token ", "calling.app")
		self.assertEqual(result, {"name": "DEV-1", "active": True})
		save.assert_called_once_with("DEV-1", "calling.app", "token")
		self.frappe.db.get_value.assert_called_once_with(
			devices.AUTHORIZATION_SOURCE, {"name": "DEV-1", "user": "user@test"}, "enabled", for_update=True
		)

	def test_register_rejects_disabled_or_foreign_credential(self) -> None:
		self.frappe.db.get_value.return_value = None
		with patch.object(devices, "save_registration") as save:
			with self.assertRaises(frappe.AuthenticationError):
				devices.register_voip_device("token", "calling.app")
			save.assert_not_called()

	def test_endpoints_reject_unauthenticated_devices(self) -> None:
		self.current.side_effect = frappe.AuthenticationError
		for method, args in (
			(devices.register_voip_device, ("token", "calling.app")),
			(devices.unregister_voip_device, ("token",)),
		):
			with self.subTest(method=method.__name__), self.assertRaises(frappe.AuthenticationError):
				method(*args)
		self.frappe.db.set_value.assert_not_called()

	def test_invalid_inputs_do_not_write(self) -> None:
		for token in (None, "", " ", "x" * 513):
			for method, args in (
				(devices.register_voip_device, (token, "calling.app")),
				(devices.unregister_voip_device, (token,)),
			):
				with (
					self.subTest(token=token, method=method.__name__),
					self.assertRaises(frappe.ValidationError),
				):
					method(*args)
		for app in (None, "", "../bad", "x" * 141):
			with self.subTest(app=app), self.assertRaises(frappe.ValidationError):
				devices.register_voip_device("token", app)
		self.frappe.db.set_value.assert_not_called()

	def test_upsert_is_idempotent_and_releases_previous_token_owner(self) -> None:
		with patch.object(devices, "now_datetime", return_value="now"):
			devices.save_registration("DEV-1", "calling.app", "token")
			created = self.frappe.get_doc.call_args.args[0]
			self.assertEqual(created["device"], "DEV-1")
			self.assertEqual(created["name"], devices.registration_name("DEV-1", "calling.app"))
			self.frappe.get_doc.return_value.insert.assert_called_once_with(
				ignore_permissions=True, set_name=created["name"]
			)
			self.frappe.db.exists.return_value = True
			devices.save_registration("DEV-1", "calling.app", "token")
		self.assertEqual(self.frappe.get_doc.call_count, 1)
		self.assertEqual(self.frappe.db.set_value.call_args.args[1], created["name"])
		self.assertEqual(self.frappe.db.set_value.call_args_list[0].args[2]["voip_token"], None)

	def test_unregister_is_scoped_to_current_device_and_token(self) -> None:
		devices.unregister_voip_device(" token ")
		self.frappe.db.set_value.assert_called_once_with(
			devices.VOIP_REGISTRATION_DOCTYPE,
			{"device": "DEV-1", "voip_token_hash": hashlib.sha256(b"token").hexdigest()},
			"voip_enabled",
			0,
			update_modified=False,
		)

	def test_recipient_lookup_filters_enabled_credentials_and_app(self) -> None:
		row = SimpleNamespace(name="REG-1", voip_token="token")
		self.frappe.get_all.side_effect = [["DEV-1"], [row]]
		self.assertEqual(devices.recipient_voip_devices("user@test", "calling.app"), [row])
		self.assertEqual(
			self.frappe.get_all.call_args_list[0].kwargs["filters"], {"user": "user@test", "enabled": 1}
		)
		self.assertEqual(
			self.frappe.get_all.call_args.kwargs["filters"],
			{
				"device": ["in", ["DEV-1"]],
				"app": "calling.app",
				"voip_enabled": 1,
			},
		)

	def test_disable_and_delete_cleanup(self) -> None:
		with patch.object(devices, "deactivate_device_voip") as deactivate:
			devices.credential_updated(SimpleNamespace(name="DEV-1", enabled=1))
			deactivate.assert_not_called()
			devices.credential_updated(SimpleNamespace(name="DEV-1", enabled=0))
			deactivate.assert_called_once_with("DEV-1")
		self.frappe.get_all.return_value = ["REG-1"]
		devices.credential_deleted(SimpleNamespace(name="DEV-1"))
		self.frappe.delete_doc.assert_called_once_with(
			devices.VOIP_REGISTRATION_DOCTYPE, "REG-1", ignore_permissions=True
		)

	def test_direct_revocation_invokes_registered_integration_callback(self) -> None:
		from flutter_utils.device_credentials import _revoke_credential

		callback = Mock()
		with (
			patch("flutter_utils.device_credentials.frappe") as auth_frappe,
			patch("flutter_utils.device_credentials.now_datetime", return_value="now"),
			patch("flutter_utils.push_notifications.deactivate_device_push"),
			patch("flutter_utils.realtime.disconnect_device_sockets"),
		):
			auth_frappe.get_hooks.return_value = ["calling.cleanup"]
			auth_frappe.get_attr.return_value = callback
			_revoke_credential("DEV-1", "Device Logout")
		callback.assert_called_once_with("DEV-1")
