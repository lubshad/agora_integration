from unittest import TestCase
from unittest.mock import patch

import frappe

from agora_integration.api.presence import set_presence


class PresenceTests(TestCase):
	def test_valid_state_writes_presence_and_last_seen(self) -> None:
		with (
			patch("agora_integration.api.presence.get_authenticated_user", return_value="u1"),
			patch("agora_integration.services.presence.frappe.db.set_value") as set_value,
		):
			result = set_presence("Background")

		self.assertEqual(result["state"], "Background")
		set_value.assert_called_once()
		args, kwargs = set_value.call_args
		self.assertEqual(args[0], "User")
		self.assertEqual(args[1], "u1")
		self.assertEqual(args[2]["agora_presence"], "Background")
		self.assertIn("agora_last_seen", args[2])
		self.assertFalse(kwargs["update_modified"])

	def test_invalid_state_is_rejected(self) -> None:
		with (
			patch("agora_integration.api.presence.get_authenticated_user", return_value="u1"),
			patch(
				"agora_integration.services.presence.frappe.throw",
				side_effect=frappe.ValidationError,
			),
		):
			with self.assertRaises(frappe.ValidationError):
				set_presence("Unknown")
