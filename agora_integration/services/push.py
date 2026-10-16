"""Incoming-call ring push owned by the calling app.

Sent when a call starts ringing and the recipient is not in the foreground.
Android receives a data-only, high-priority FCM message so the app builds its
own ringing UI; iOS receives a PushKit VoIP push (CallKit) when a VoIP token is
registered, or an FCM alert as a fallback. A dismiss push is sent when the call
leaves the ringing state so a terminated device stops ringing.
"""

from datetime import timedelta
from typing import Any

import frappe

from agora_integration.services.voip_devices import VOIP_REGISTRATION_DOCTYPE, recipient_voip_devices

REGISTRATION_DOCTYPE = "Flutter Device Credential"
IOS_CALL_CATEGORY = "agora_call"
PUSH_TTL_SECONDS = 45
DEDUPE_SECONDS = 60
DISMISS_DEDUPE_SECONDS = 30
#: States after which the recipient's ringing UI must be dismissed.
DISMISS_STATES = ("Ended", "Declined", "Cancelled", "Timed Out", "Failed")


def enqueue_ring_push(call: Any) -> None:
	"""Queue the ring push after commit so a rolled-back call never rings."""
	if not getattr(call, "recipient", None):
		return
	frappe.enqueue(
		"agora_integration.services.push.send_ring_push",
		enqueue_after_commit=True,
		call=call.name,
	)


def enqueue_call_dismiss(call: Any) -> None:
	"""Queue the dismiss push after commit so a finished call stops ringing."""
	if not getattr(call, "recipient", None):
		return
	frappe.enqueue(
		"agora_integration.services.push.send_call_dismiss",
		enqueue_after_commit=True,
		call=call.name,
	)


def _load_session(call: str) -> Any:
	return frappe.db.get_value(
		"Agora Call Session",
		call,
		["name", "caller", "recipient", "mode", "state", "project"],
		as_dict=True,
	)


def send_ring_push(call: str) -> None:
	settings = frappe.get_single("Flutter Utils Settings")
	if not settings.get("enable_firebase_push"):
		return
	if frappe.cache.get_value(_dedupe_key(call)):
		return
	session = _load_session(call)
	if not session or not session.recipient:
		return
	tokens = _recipient_tokens(session.recipient, session.project)
	voip = _recipient_voip(session.recipient, session.project)
	if not tokens and not voip:
		return
	if voip:
		_safe_voip(session, voip, "ring", call)
	if tokens:
		_safe_fcm(settings, session, tokens, event="incoming_call", label=call)
	frappe.cache.set_value(_dedupe_key(call), 1, expires_in_sec=DEDUPE_SECONDS)


def send_call_dismiss(call: str) -> None:
	settings = frappe.get_single("Flutter Utils Settings")
	if not settings.get("enable_firebase_push"):
		return
	if frappe.cache.get_value(_dismiss_key(call)):
		return
	session = _load_session(call)
	if not session or not session.recipient:
		return
	tokens = _recipient_tokens(session.recipient, session.project)
	voip = _recipient_voip(session.recipient, session.project)
	if not tokens and not voip:
		return
	if voip:
		_safe_voip(session, voip, "end", call)
	if tokens:
		_safe_fcm(settings, session, tokens, event="call_ended", label=call)
	frappe.cache.set_value(_dismiss_key(call), 1, expires_in_sec=DISMISS_DEDUPE_SECONDS)


def _safe_voip(session: Any, rows: list[Any], action: str, call: str) -> None:
	try:
		_deliver_voip(session, rows, action)
	except Exception:
		frappe.log_error(title="agora_integration.push", message=f"Call VoIP push failed for {call}")


def _safe_fcm(
	settings: Any, session: Any, tokens: list[str], *, event: str, label: str
) -> None:
	try:
		from firebase_admin import messaging
		from flutter_utils.firebase import get_firebase_app

		_deliver(messaging, get_firebase_app(settings), session, tokens, event=event)
	except Exception:
		frappe.log_error(title="agora_integration.push", message=f"Call push failed for {label}")


def _deliver(
	messaging: Any,
	firebase_app: Any,
	session: Any,
	tokens: list[str],
	event: str = "incoming_call",
) -> None:
	caller_name = frappe.db.get_value("User", session.caller, "first_name") or "Someone"
	messaging.send_each_for_multicast(
		messaging.MulticastMessage(
			tokens=tokens,
			data={
				"type": event,
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


def _deliver_voip(session: Any, rows: list[Any], action: str) -> None:
	from agora_integration.services import apns

	payload = apns.build_payload(
		call_id=str(session.name),
		name=frappe.db.get_value("User", session.caller, "first_name") or "Someone",
		mode=str(session.mode),
		handle=str(session.caller or ""),
		action=action,
	)
	dead = apns.send_voip_push([row.voip_token for row in rows], payload)
	for row in rows:
		if row.voip_token in dead:
			frappe.db.set_value(
				VOIP_REGISTRATION_DOCTYPE, row.name, "voip_enabled", 0, update_modified=False
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


def _recipient_voip(user: str, project: str | None) -> list[Any]:
	return recipient_voip_devices(user, project)


def _dedupe_key(call_id: str) -> str:
	return f"agora_integration:call_push:{call_id}"


def _dismiss_key(call_id: str) -> str:
	return f"agora_integration:call_dismiss:{call_id}"
