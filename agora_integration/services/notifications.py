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
		# Any installed app can own its ring notification via this generic hook.
		# A handler returns True when it handled the push, so the default below
		# is only used when no app claims it (project-scoped by the handler).
		handlers = frappe.get_hooks("agora_call_ringing_notification") or []
		if not any(frappe.get_attr(path)(call) for path in handlers):
			enqueue_push_notifications(
				users=[call.recipient],
				title="Incoming call",
				body=f"Incoming {call.mode} call",
				app=call.project,
				data={key: str(value) for key, value in payload.items()},
			)
