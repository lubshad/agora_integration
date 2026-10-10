from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now, now_datetime

PRESENCE_STATES = ("Foreground", "Background", "Offline")
DEFAULT_STALE_SECONDS = 120


def set_presence(user: str, state: str) -> dict[str, Any]:
	"""Record the user's app presence (Foreground / Background / Offline)."""
	if state not in PRESENCE_STATES:
		frappe.throw(_("Invalid presence state."))
	timestamp = now()
	frappe.db.set_value(
		"User",
		user,
		{"agora_presence": state, "agora_last_seen": timestamp},
		update_modified=False,
	)
	return {"state": state, "last_seen": str(timestamp)}


def get_presence(user: str) -> str:
	"""Effective presence; a stale report is treated as ``Offline``.

	The app reports on lifecycle/socket changes, so a crash can leave the last
	state behind. ``agora_last_seen`` lets a stale report decay to Offline.
	"""
	row = frappe.db.get_value("User", user, ["agora_presence", "agora_last_seen"], as_dict=True)
	if not row or not row.agora_presence:
		return "Offline"
	if _is_stale(row.agora_last_seen):
		return "Offline"
	return row.agora_presence


def _is_stale(last_seen: Any) -> bool:
	if not last_seen:
		return True
	age = (now_datetime() - get_datetime(last_seen)).total_seconds()
	return age > _stale_seconds()


def _stale_seconds() -> int:
	try:
		value = frappe.db.get_single_value("Agora Settings", "presence_stale_after")
	except Exception:
		return DEFAULT_STALE_SECONDS
	return int(value) if value else DEFAULT_STALE_SECONDS
