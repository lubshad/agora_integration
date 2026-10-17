"""Calling-owned PushKit registrations, linked to generic managed credentials."""

import hashlib
import re
from typing import Any

import frappe
from flutter_utils.device_credentials import AUTHORIZATION_SOURCE, get_current_device_credential
from frappe import _
from frappe.utils import now_datetime

VOIP_REGISTRATION_DOCTYPE = "Agora VoIP Device"


def _clean_token(token: str) -> str:
	if not isinstance(token, str) or not token.strip() or len(token) > 512:
		frappe.throw(_("VoIP token is invalid."))
	return token.strip()


def registration_name(device: str, app: str) -> str:
	return hashlib.sha256(f"{device}\0{app}".encode()).hexdigest()


def save_registration(device: str, app: str, token: str, enabled: int = 1, last_seen: Any = None) -> None:
	"""Upsert one registration per installation/app; unique hashes prevent double ownership."""
	name = registration_name(device, app)
	token_hash = hashlib.sha256(token.encode()).hexdigest()
	frappe.db.set_value(
		VOIP_REGISTRATION_DOCTYPE,
		{"voip_token_hash": token_hash, "name": ["!=", name]},
		{"voip_token": None, "voip_token_hash": None, "voip_enabled": 0},
		update_modified=False,
	)
	values = {
		"device": device,
		"app": app,
		"voip_token": token,
		"voip_token_hash": token_hash,
		"voip_enabled": enabled,
		"voip_last_seen_at": last_seen or now_datetime(),
	}
	if frappe.db.exists(VOIP_REGISTRATION_DOCTYPE, name):
		frappe.db.set_value(VOIP_REGISTRATION_DOCTYPE, name, values, update_modified=False)
	else:
		frappe.get_doc({"doctype": VOIP_REGISTRATION_DOCTYPE, "name": name, **values}).insert(
			ignore_permissions=True, set_name=name
		)


@frappe.whitelist(methods=["POST"])
def register_voip_device(token: str, app: str) -> dict[str, Any]:
	device = get_current_device_credential()
	token = _clean_token(token)
	if not isinstance(app, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,139}", app):
		frappe.throw(_("Application identifier is invalid."))
	# Serialize refresh against logout/device-limit revocation and check ownership again.
	if not frappe.db.get_value(
		AUTHORIZATION_SOURCE,
		{"name": device, "user": frappe.session.user},
		"enabled",
		for_update=True,
	):
		raise frappe.AuthenticationError
	save_registration(device, app, token)
	# Preserve the original API response's managed-device identity.
	return {"name": device, "active": True}


@frappe.whitelist(methods=["POST"])
def unregister_voip_device(token: str) -> None:
	device = get_current_device_credential()
	token = _clean_token(token)
	frappe.db.set_value(
		VOIP_REGISTRATION_DOCTYPE,
		{"device": device, "voip_token_hash": hashlib.sha256(token.encode()).hexdigest()},
		"voip_enabled",
		0,
		update_modified=False,
	)


def deactivate_device_voip(device: str) -> None:
	# May be invoked during migration before Agora's new table has been synced.
	if frappe.db.table_exists(VOIP_REGISTRATION_DOCTYPE):
		frappe.db.set_value(
			VOIP_REGISTRATION_DOCTYPE, {"device": device}, "voip_enabled", 0, update_modified=False
		)


def credential_updated(doc: Any, method: str | None = None) -> None:
	if not doc.enabled:
		deactivate_device_voip(doc.name)


def credential_deleted(doc: Any, method: str | None = None) -> None:
	# Remove linked registrations so deleting a managed credential is not blocked.
	if frappe.db.table_exists(VOIP_REGISTRATION_DOCTYPE):
		for name in frappe.get_all(VOIP_REGISTRATION_DOCTYPE, filters={"device": doc.name}, pluck="name"):
			frappe.delete_doc(VOIP_REGISTRATION_DOCTYPE, name, ignore_permissions=True)


def recipient_voip_devices(user: str, app: str | None) -> list[Any]:
	devices = frappe.get_all(AUTHORIZATION_SOURCE, filters={"user": user, "enabled": 1}, pluck="name")
	if not devices:
		return []
	filters: dict[str, Any] = {"device": ["in", devices], "voip_enabled": 1}
	if app:
		filters["app"] = app
	return [
		row
		for row in frappe.get_all(VOIP_REGISTRATION_DOCTYPE, filters=filters, fields=["name", "voip_token"])
		if row.voip_token
	]
