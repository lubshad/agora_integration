"""Database-backed checks; run with an initialized, migrated Frappe site."""

from unittest import TestCase, skipUnless
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from agora_integration.patches.v1_0 import move_voip_from_flutter_utils as migration
from agora_integration.services import voip_devices as devices


@skipUnless(getattr(frappe.local, "db", None), "Requires an initialized Frappe site")
class VoipIntegrationTests(TestCase):
	def setUp(self) -> None:
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.savepoint = "voip_test"
		frappe.db.savepoint(self.savepoint)
		self.app = f"voip.test.{frappe.generate_hash(length=10)}"
		self.device = self._device()
		self.auth = patch.object(devices, "get_current_device_credential", return_value=self.device.name)
		self.auth.start()

	def tearDown(self) -> None:
		self.auth.stop()
		frappe.db.rollback(save_point=self.savepoint)
		for doctype in ("Agora Settings", "Flutter Utils Settings"):
			frappe.clear_document_cache(doctype, doctype)
		frappe.set_user(self.previous_user)

	def _device(self) -> Document:
		return frappe.get_doc(
			{
				"doctype": "Flutter Device Credential",
				"user": "Administrator",
				"enabled": 1,
				"last_login_at": now_datetime(),
				"api_key": frappe.generate_hash(length=32),
				"api_secret": frappe.generate_hash(length=32),
				"device_id_hash": frappe.generate_hash(length=64),
				"device_key": frappe.generate_hash(length=64),
			}
		).insert(ignore_permissions=True)

	def test_registration_retry_token_transfer_unregister_and_disable(self) -> None:
		devices.register_voip_device("test-token", self.app)
		devices.register_voip_device("test-token", self.app)
		name = devices.registration_name(self.device.name, self.app)
		self.assertTrue(frappe.db.exists(devices.VOIP_REGISTRATION_DOCTYPE, name))
		self.assertEqual(frappe.db.count(devices.VOIP_REGISTRATION_DOCTYPE, {"device": self.device.name}), 1)
		other = self._device()
		with patch.object(devices, "get_current_device_credential", return_value=other.name):
			devices.register_voip_device("test-token", self.app)
		self.assertFalse(frappe.db.get_value(devices.VOIP_REGISTRATION_DOCTYPE, name, "voip_enabled"))
		# A previous owner cannot unregister a transferred token.
		devices.unregister_voip_device("test-token")
		other_name = devices.registration_name(other.name, self.app)
		self.assertTrue(frappe.db.get_value(devices.VOIP_REGISTRATION_DOCTYPE, other_name, "voip_enabled"))
		other.enabled = 0
		other.save(ignore_permissions=True)
		self.assertFalse(frappe.db.get_value(devices.VOIP_REGISTRATION_DOCTYPE, other_name, "voip_enabled"))
		self.assertEqual(devices.recipient_voip_devices("Administrator", self.app), [])

	def test_direct_revocation_and_delete_cleanup(self) -> None:
		from flutter_utils.device_credentials import _revoke_credential

		devices.register_voip_device("test-token", self.app)
		with patch("flutter_utils.realtime.disconnect_device_sockets"):
			_revoke_credential(self.device.name, "Device Logout")
		name = devices.registration_name(self.device.name, self.app)
		self.assertFalse(frappe.db.get_value(devices.VOIP_REGISTRATION_DOCTYPE, name, "voip_enabled"))
		with patch("flutter_utils.realtime.disconnect_device_sockets"):
			frappe.delete_doc("Flutter Device Credential", self.device.name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists(devices.VOIP_REGISTRATION_DOCTYPE, name))

	def test_registration_rolls_back_with_request(self) -> None:
		frappe.db.savepoint("registration_request")
		devices.register_voip_device("test-token", self.app)
		frappe.db.rollback(save_point="registration_request")
		self.assertFalse(
			frappe.db.exists(
				devices.VOIP_REGISTRATION_DOCTYPE, devices.registration_name(self.device.name, self.app)
			)
		)

	def test_settings_migration_encrypts_key_and_is_idempotent(self) -> None:
		for field in migration.APNS_FIELDS:
			frappe.db.set_single_value("Agora Settings", field, None)
		from frappe.utils.password import remove_encrypted_password

		remove_encrypted_password("Agora Settings", "Agora Settings", "apns_private_key")
		frappe.db.set_single_value(
			"Flutter Utils Settings",
			{
				"apns_team_id": "TEAM",
				"apns_key_id": "KEY",
				"apns_voip_bundle_id": "",
				"apns_use_sandbox": 1,
				"app_identifier": "com.example.test",
			},
		)
		set_encrypted_password(
			"Flutter Utils Settings", "Flutter Utils Settings", "test-key", "apns_private_key"
		)
		migration.execute()
		self.assertEqual(
			get_decrypted_password("Agora Settings", "Agora Settings", "apns_private_key"), "test-key"
		)

		self.assertEqual(
			frappe.db.get_single_value("Agora Settings", "apns_voip_bundle_id"), "com.example.test"
		)
		self.assertIsNone(
			get_decrypted_password(
				"Flutter Utils Settings", "Flutter Utils Settings", "apns_private_key", raise_exception=False
			)
		)
		migration.execute()
		self.assertEqual(
			get_decrypted_password("Agora Settings", "Agora Settings", "apns_private_key"), "test-key"
		)

	def test_legacy_device_token_migrates_after_metadata_removal(self) -> None:
		if not frappe.db.has_column("Flutter Device Credential", "voip_token"):
			self.skipTest("Fresh schema has no legacy VoIP columns")
		frappe.db.set_value(
			"Flutter Device Credential",
			self.device.name,
			{
				"app": self.app,
				"voip_token": "legacy-test-token",
				"voip_enabled": 1,
				"voip_last_seen_at": now_datetime(),
			},
		)
		migration._move_devices()
		name = devices.registration_name(self.device.name, self.app)
		self.assertEqual(
			frappe.db.get_value(devices.VOIP_REGISTRATION_DOCTYPE, name, "voip_token"), "legacy-test-token"
		)
		self.assertIsNone(frappe.db.get_value("Flutter Device Credential", self.device.name, "voip_token"))
		migration._move_devices()
		self.assertEqual(frappe.db.count(devices.VOIP_REGISTRATION_DOCTYPE, {"device": self.device.name}), 1)
