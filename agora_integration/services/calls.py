"""Internal, transaction-bound user-to-user calling services. No HTTP exposure."""

import hashlib
import secrets
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime, time_diff_in_seconds

from agora_integration.services.notifications import notify
from agora_integration.services.tokens import get_settings, issue_token

ACTIVE = ("Ringing", "Connecting", "Active")
Policy = Callable[[Any, str], None]


def _user() -> str:
	user = frappe.session.user
	if user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	return user


def _device() -> str:
	from flutter_utils.device_credentials import get_current_device_credential

	return get_current_device_credential()


def serialize(call: Any, display: dict[str, str] | None = None) -> dict[str, Any]:
	user = frappe.session.user
	if display is None:
		names = frappe.get_all(
			"User", filters={"name": ["in", [call.caller, call.recipient]]}, fields=["name", "first_name"]
		)
		display = {row.name: row.first_name for row in names}
	end = call.ended_at or now_datetime()
	visible_state = call.state
	if call.state in ("Ringing", "Connecting") and get_datetime(call.deadline) <= now_datetime():
		# Do not offer stale invitations while waiting for the scheduled persisted expiry.
		visible_state = "Timed Out" if call.state == "Ringing" else "Failed"
	return {
		"id": call.name,
		"state": visible_state,
		"version": int(call.version),
		"mode": call.mode,
		"caller": call.caller,
		"recipient": call.recipient,
		"caller_name": display.get(call.caller, ""),
		"recipient_name": display.get(call.recipient, ""),
		"incoming": user == call.recipient,
		"expires_at": str(call.deadline or ""),
		"can_join": any(row.user == user and row.device == _device() for row in call.participants),
		"started_at": str(call.started_at or ""),
		"ended_at": str(call.ended_at or ""),
		"duration": max(0, int(time_diff_in_seconds(end, call.started_at))) if call.started_at else 0,
		"end_reason": call.end_reason or "",
		"unpaid": True,
	}


def _save(call: Any, previous: str | None = None) -> None:
	call.version = int(call.version or 0) + 1
	call.save(ignore_permissions=True)
	if previous != call.state:
		frappe.get_doc(
			{
				"doctype": "Agora Call Event",
				"call": call.name,
				"actor": frappe.session.user,
				"state": call.state,
				"version": call.version,
				"reason": call.end_reason,
			}
		).insert(ignore_permissions=True)
		notify(call)


def expire(call: Any) -> bool:
	"""Called with the session row locked; terminal transitions release busy state."""
	if call.state not in ACTIVE:
		return False
	now = now_datetime()
	previous = call.state
	if call.state in ("Ringing", "Connecting") and get_datetime(call.deadline) <= now:
		call.state = "Timed Out" if call.state == "Ringing" else "Failed"
		call.end_reason = "Invitation expired" if previous == "Ringing" else "Connection timeout"
	elif call.state == "Active":
		timeout = int(frappe.get_single("Agora Settings").heartbeat_timeout or 90)
		if all(
			row.last_seen
			and time_diff_in_seconds(now, row.last_seen) <= timeout
			and (not row.disconnected_at or time_diff_in_seconds(now, row.disconnected_at) <= timeout)
			for row in call.participants
		):
			return False
		call.state = "Ended"
		call.end_reason = "Connection lost"
	else:
		return False
	call.ended_at = now
	_save(call, previous)
	return True


def _load(call_id: str, project: str, lock: bool = True) -> Any:
	user = _user()
	call = frappe.get_doc("Agora Call Session", call_id)
	if call.project != project or user not in (call.caller, call.recipient):
		frappe.throw(_("You cannot access this call."), frappe.PermissionError)
	if lock:
		for participant in sorted((call.caller, call.recipient)):
			frappe.db.get_value("User", participant, "enabled", for_update=True)
		call = frappe.get_doc("Agora Call Session", call_id, for_update=True)
		expire(call)
	return call


def start_call(project: str, recipient: str, mode: str, request_id: str, policy: Policy) -> dict[str, Any]:
	caller = _user()
	if mode not in ("audio", "video") or recipient == caller:
		frappe.throw(_("Invalid call request."))
	try:
		request_id = str(UUID(request_id))
	except ValueError, TypeError, AttributeError:
		frappe.throw(_("A valid installation-generated request UUID is required."))
	settings = get_settings()
	# Stable User row lock ordering serializes reservations, including calls across projects.
	for user in sorted((caller, recipient)):
		if not frappe.db.get_value("User", user, "enabled", for_update=True):
			frappe.throw(_("This user is unavailable."))
	key = hashlib.sha256(f"{project}:{caller}:{request_id}".encode()).hexdigest()
	existing = frappe.db.get_value("Agora Call Session", {"request_key": key}, "name", for_update=True)
	if existing:
		call = _load(existing, project)
		if call.recipient != recipient or call.mode != mode:
			frappe.throw(_("Request UUID already belongs to another call."))
		return serialize(call)
	call = frappe.get_doc(
		{
			"doctype": "Agora Call Session",
			"project": project,
			"caller": caller,
			"recipient": recipient,
			"mode": mode,
			"request_key": key,
			"channel": f"call_{uuid4().hex}",
			"state": "Ringing",
			"version": 1,
			"deadline": add_to_date(now_datetime(), seconds=int(settings.ring_timeout or 45)),
		}
	)
	policy(call, "start")
	busy_rows = frappe.qb.get_query(
		"Agora Call Session",
		filters={"state": ["in", ACTIVE]},
		or_filters={"caller": ["in", [caller, recipient]], "recipient": ["in", [caller, recipient]]},
		fields=["name"],
		for_update=True,
	).run(as_dict=True)
	for row in busy_rows:
		name = row.name
		active = frappe.get_doc("Agora Call Session", name, for_update=True)
		if not expire(active):
			frappe.throw(_("One of the participants is already in a call."))
	uids = secrets.SystemRandom().sample(range(1, 2**31), 2)
	for index, user in enumerate((caller, recipient)):
		call.append(
			"participants", {"user": user, "uid": uids[index], "device": _device() if index == 0 else None}
		)
	call.insert(ignore_permissions=True)
	frappe.get_doc(
		{"doctype": "Agora Call Event", "call": call.name, "actor": caller, "state": "Ringing", "version": 1}
	).insert(ignore_permissions=True)
	notify(call)
	return serialize(call)


def get_call(call_id: str, project: str) -> dict[str, Any]:
	# Read operations do not mutate state; scheduler/actions expire sessions.
	return serialize(_load(call_id, project, lock=False))


def get_active_call(project: str) -> dict[str, Any] | None:
	user = _user()
	names = frappe.get_all(
		"Agora Call Session",
		filters={"project": project, "state": ["in", ACTIVE]},
		or_filters={"caller": user, "recipient": user},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return get_call(names[0], project) if names else None


def act(call_id: str, project: str, action: str, policy: Policy) -> dict[str, Any]:
	call = _load(call_id, project)
	user = _user()
	previous = call.state
	if action not in ("accept", "decline", "cancel", "end"):
		frappe.throw(_("Invalid call action."))
	if action in ("accept", "decline") and user != call.recipient:
		frappe.throw(_("Only the recipient can respond."), frappe.PermissionError)
	if action == "cancel" and user != call.caller:
		frappe.throw(_("Only the caller can cancel."), frappe.PermissionError)
	if call.state not in ACTIVE:
		return serialize(call)
	if action == "accept":
		policy(call, "accept")
		participant = next(row for row in call.participants if row.user == user)
		device = _device()
		if participant.device and participant.device != device:
			frappe.throw(_("This call was accepted on another device."), frappe.PermissionError)
		if call.state == "Ringing":
			participant.device = device
			call.state = "Connecting"
			call.deadline = add_to_date(now_datetime(), seconds=int(get_settings().connect_timeout or 45))
		else:
			return serialize(call)
	elif action in ("decline", "cancel"):
		if call.state != "Ringing":
			frappe.throw(_("The invitation is no longer ringing."))
		call.state = "Declined" if action == "decline" else "Cancelled"
		call.end_reason = call.state
		call.ended_at = now_datetime()
	else:
		call.state = "Ended"
		call.end_reason = "Participant ended call"
		call.ended_at = now_datetime()
	_save(call, previous)
	return serialize(call)


def renew_call_token(call_id: str, project: str, policy: Policy) -> dict[str, Any]:
	call = _load(call_id, project)
	if call.state not in ("Connecting", "Active"):
		frappe.throw(_("This call cannot issue a media token."))
	policy(call, "token")
	participant = next(row for row in call.participants if row.user == _user())
	if participant.device != _device():
		frappe.throw(_("This call belongs to another device."), frappe.PermissionError)
	return issue_token(call.channel, int(participant.uid))


def report_connection(call_id: str, project: str, connected: bool, policy: Policy) -> dict[str, Any]:
	call = _load(call_id, project)
	if call.state not in ("Connecting", "Active"):
		return serialize(call)
	policy(call, "connection")
	participant = next(row for row in call.participants if row.user == _user())
	if participant.device != _device():
		frappe.throw(_("This call belongs to another device."), frappe.PermissionError)
	previous = call.state
	if connected:
		participant.disconnected_at = None
	elif not participant.disconnected_at:
		participant.disconnected_at = now_datetime()
	participant.connected = bool(connected)
	participant.last_seen = now_datetime()
	if connected and not participant.joined_at:
		participant.joined_at = now_datetime()
	if call.state == "Connecting" and all(row.connected for row in call.participants):
		call.state = "Active"
		call.started_at = now_datetime()
	_save(call, previous)
	return serialize(call)


def list_call_history(project: str, start: int = 0, limit: int = 20) -> list[dict[str, Any]]:
	user = _user()
	start, limit = max(0, int(start)), min(50, max(1, int(limit)))
	names = frappe.get_all(
		"Agora Call Session",
		filters={"project": project},
		or_filters={"caller": user, "recipient": user},
		pluck="name",
		order_by="creation desc",
		limit_start=start,
		limit_page_length=limit,
	)
	if not names:
		return []
	records = frappe.get_all(
		"Agora Call Session", filters={"name": ["in", names]}, fields=["*"], order_by="creation desc"
	)
	participants = frappe.get_all(
		"Agora Call Participant",
		filters={"parent": ["in", names], "parenttype": "Agora Call Session"},
		fields=["parent", "user", "device"],
	)
	users = {row.caller for row in records} | {row.recipient for row in records}
	display = {
		row.name: row.first_name
		for row in frappe.get_all(
			"User", filters={"name": ["in", list(users)]}, fields=["name", "first_name"]
		)
	}
	for record in records:
		record.participants = [row for row in participants if row.parent == record.name]
	return [serialize(record, display) for record in records]
