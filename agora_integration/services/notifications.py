from typing import Any

import frappe
from flutter_utils.push_notifications import enqueue_push_notifications


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
	if call.state == "Ringing":
		enqueue_push_notifications(
			users=[call.recipient],
			title="Incoming call",
			body=f"Incoming {call.mode} call",
			app=call.project,
			data={key: str(value) for key, value in payload.items()},
		)
