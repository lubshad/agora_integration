from typing import Any

import frappe

from agora_integration.services.presence import get_presence
from agora_integration.services.push import (
	DISMISS_STATES,
	enqueue_call_dismiss,
	enqueue_ring_push,
)


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
	# Skip pushes while the recipient is actively using the app: the realtime
	# event above already drives the in-app ringing UI. Background and offline
	# recipients get a push so the OS can ring (or stop ringing).
	if call.state == "Ringing":
		if get_presence(call.recipient) != "Foreground":
			enqueue_ring_push(call)
	elif call.state in DISMISS_STATES:
		if get_presence(call.recipient) != "Foreground":
			enqueue_call_dismiss(call)
