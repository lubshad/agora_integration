from unittest import TestCase
from unittest.mock import patch

import frappe

from agora_integration.patches.v1_0 import move_voip_from_flutter_utils as migration


class VoipMigrationTests(TestCase):
	def test_settings_preserve_destination_and_copy_secret_and_bundle_fallback(self) -> None:
		with (
			patch.object(migration, "frappe") as framework,
			patch.object(migration, "get_decrypted_password", side_effect=["legacy-secret", None]),
			patch.object(migration, "set_encrypted_password") as encrypt,
			patch.object(migration, "remove_encrypted_password") as remove,
		):
			framework.db.get_singles_dict.side_effect = [
				{"apns_team_id": "OLD", "apns_key_id": "KEY", "app_identifier": "com.example.app"},
				{"apns_team_id": "NEW"},
			]
			migration._move_settings()
			writes = [call.args for call in framework.db.set_single_value.call_args_list]
			self.assertNotIn(("Agora Settings", "apns_team_id", "OLD"), writes)
			self.assertIn(("Agora Settings", "apns_voip_bundle_id", "com.example.app"), writes)
			encrypt.assert_called_once_with(
				"Agora Settings", "Agora Settings", "legacy-secret", "apns_private_key"
			)
			remove.assert_called_once()

	def test_device_migration_skips_existing_registration_on_rerun(self) -> None:
		row = frappe._dict(
			name="DEV-1", app="app", enabled=0, voip_enabled=1, voip_token="token", voip_last_seen_at="then"
		)
		with (
			patch.object(migration, "frappe") as framework,
			patch.object(migration, "save_registration") as save,
		):
			framework.get_all.return_value = [row]
			framework.db.exists.return_value = False
			migration._move_devices()
			save.assert_called_once_with("DEV-1", "app", "token", 0, "then")
			self.assertIsNone(framework.db.set_value.call_args.args[2]["voip_token"])
			framework.db.exists.return_value = True
			save.reset_mock()
			migration._move_devices()
			save.assert_not_called()

	def test_fresh_install_without_legacy_columns(self) -> None:
		with patch.object(migration, "frappe") as framework:
			framework.db.has_column.return_value = False
			migration._move_devices()
			framework.get_all.assert_not_called()
