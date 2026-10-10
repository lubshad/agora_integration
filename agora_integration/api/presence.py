from typing import Any

import frappe

from agora_integration.api._utils import get_authenticated_user
from agora_integration.services import presence


@frappe.whitelist(methods=["POST"])
def set_presence(state: str) -> dict[str, Any]:
	"""Record the signed-in caller's app presence (from lifecycle/socket)."""
	return presence.set_presence(get_authenticated_user(), state)
