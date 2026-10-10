"""Generic incoming-call ring push owned by the calling app.

Sent when a call starts ringing and the recipient is not in the foreground
(foreground clients receive the realtime event and show the in-app ring).
Android is data-only, high priority, so the app builds the ringing
notification with Accept/Decline; iOS carries an alert with an action
category.
"""

from datetime import timedelta
from typing import Any

import frappe

REGISTRATION_DOCTYPE = "Flutter Device Credential"
IOS_CALL_CATEGORY = "agora_call"
PUSH_TTL_SECONDS = 45
DEDUPE_SECONDS = 60


def enqueue_ring_push(call: Any) -> None:
	"""Queue the ring push after commit so a rolled-back call never rings."""
	if not getattr(call, "recipient", None):
		return
	frappe.enqueue(
		"agora_integration.services.push.send_ring_push",
		enqueue_after_commit=True,
		call=call.name,
	)


def send_ring_push(call: str) -> None:
	settings = frappe.get_single("Flutter Utils Settings")
	if not settings.get("enable_firebase_push"):
		return
	if frappe.cache.get_value(_dedupe_key(call)):
		return
	session = frappe.db.get_value(
		"Agora Call Session",
		call,
		["name", "caller", "recipient", "mode", "state", "project"],
		as_dict=True,
	)
	if not session or not session.recipient:
		return
	tokens = _recipient_tokens(session.recipient, session.project)
	if not tokens:
		return
	try:
		from firebase_admin import messaging
		from flutter_utils.firebase import get_firebase_app
	except Exception:
		frappe.log_error(title="agora_integration.push", message="Firebase is unavailable.")
		return
	try:
		_deliver(messaging, get_firebase_app(settings), session, tokens)
		frappe.cache.set_value(_dedupe_key(call), 1, expires_in_sec=DEDUPE_SECONDS)
	except Exception:
		frappe.log_error(title="agora_integration.push", message=f"Call push failed for {call}")


def _deliver(messaging: Any, firebase_app: Any, session: Any, tokens: list[str]) -> None:
	caller_name = frappe.db.get_value("User", session.caller, "first_name") or "Someone"
	messaging.send_each_for_multicast(
		messaging.MulticastMessage(
			tokens=tokens,
			data={
				"type": "incoming_call",
				"call_id": str(session.name),
				"mode": str(session.mode),
				"name": caller_name,
				"project": str(session.project or ""),
				"state": str(session.state),
			},
			android=messaging.AndroidConfig(
				priority="high",
				ttl=timedelta(seconds=PUSH_TTL_SECONDS),
			),
			apns=messaging.APNSConfig(
				headers={"apns-priority": "10", "apns-push-type": "alert"},
				payload=messaging.APNSPayload(
					aps=messaging.Aps(
						alert=messaging.ApsAlert(
							title="Incoming call",
							body=f"Incoming {session.mode} call",
						),
						sound="default",
						category=IOS_CALL_CATEGORY,
						content_available=True,
					)
				),
			),
		),
		app=firebase_app,
	)


def _recipient_tokens(user: str, project: str | None) -> list[str]:
	filters: dict[str, Any] = {"user": user, "enabled": 1, "push_enabled": 1}
	if project:
		filters["app"] = project
	return [
		row.fcm_token
		for row in frappe.get_all(REGISTRATION_DOCTYPE, filters=filters, fields=["fcm_token"])
		if row.fcm_token
	]


def _dedupe_key(call_id: str) -> str:
	return f"agora_integration:call_push:{call_id}"
