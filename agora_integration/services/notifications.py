from typing import Any

import frappe

from agora_integration.services.presence import get_presence
from agora_integration.services.push import enqueue_ring_push


def notify(call: Any) -> None:
	payload = {
		"call_id": call.name,
		"state": call.state,
		"version": call.version,
		"project": call.project,
		"expires_at": str(call.deadline or ""),
	}
	for user in (call.caller, call.recipient):
		frappe.publish_realtime("agora_call_updated", payload, user=user, after_commit=True)
	# Skip the ring push while the recipient is actively using the app: the
	# realtime event above already drives the in-app ringing UI. Background and
	# offline recipients get a data-only push so the OS can ring them.
	if call.state == "Ringing" and get_presence(call.recipient) != "Foreground":
		enqueue_ring_push(call)
