import re

import frappe
from frappe import _
from frappe.model.document import Document


class AgoraSettings(Document):
	def validate(self) -> None:
		for field, lower, upper in (
			("token_ttl", 60, 3600),
			("ring_timeout", 15, 120),
			("connect_timeout", 15, 120),
			("heartbeat_timeout", 30, 300),
		):
			if not lower <= int(self.get(field) or 0) <= upper:
				frappe.throw(_("{0} must be between {1} and {2} seconds.").format(field, lower, upper))
		if self.enabled:
			certificate = self.get_password("app_certificate", raise_exception=False) or ""
			if not all(re.fullmatch(r"[a-fA-F0-9]{32}", value or "") for value in (self.app_id, certificate)):
				frappe.throw(_("Valid Agora App ID and App Certificate are required."))
