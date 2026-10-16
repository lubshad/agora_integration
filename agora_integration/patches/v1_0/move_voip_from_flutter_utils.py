"""Transfer calling data out of generic authentication/FCM settings.

The legacy fields are removed from source metadata, but Frappe retains database
columns and Singles rows. Read those directly so migration works in either app
sync order. Never drop columns or overwrite existing Agora registrations/settings.
"""

import hashlib

import frappe
from frappe.utils import cint
from frappe.utils.password import (
	get_decrypted_password,
	remove_encrypted_password,
	set_encrypted_password,
)

from agora_integration.services.voip_devices import (
	AUTHORIZATION_SOURCE,
	VOIP_REGISTRATION_DOCTYPE,
	registration_name,
	save_registration,
)

LEGACY_SETTINGS = "Flutter Utils Settings"
SETTINGS = "Agora Settings"
APNS_FIELDS = ("apns_team_id", "apns_key_id", "apns_voip_bundle_id", "apns_use_sandbox")


def execute() -> None:
	_move_settings()
	_move_devices()


def _move_settings() -> None:
	legacy = frappe.db.get_singles_dict(LEGACY_SETTINGS)
	current = frappe.db.get_singles_dict(SETTINGS)
	# Preserve the old implicit bundle fallback as an explicit Agora setting.
	if any(legacy.get(field) for field in APNS_FIELDS):
		legacy["apns_voip_bundle_id"] = legacy.get("apns_voip_bundle_id") or legacy.get("app_identifier")
	for field in APNS_FIELDS:
		if legacy.get(field) and not current.get(field):
			frappe.db.set_single_value(SETTINGS, field, legacy[field])
	key = get_decrypted_password(LEGACY_SETTINGS, LEGACY_SETTINGS, "apns_private_key", raise_exception=False)
	if key and not get_decrypted_password(SETTINGS, SETTINGS, "apns_private_key", raise_exception=False):
		set_encrypted_password(SETTINGS, SETTINGS, key, "apns_private_key")
		frappe.db.set_single_value(SETTINGS, "apns_private_key", "********")
	remove_encrypted_password(LEGACY_SETTINGS, LEGACY_SETTINGS, "apns_private_key")
	for field in (*APNS_FIELDS, "apns_private_key"):
		frappe.db.delete("Singles", {"doctype": LEGACY_SETTINGS, "field": field})
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	frappe.clear_document_cache(LEGACY_SETTINGS, LEGACY_SETTINGS)


def _move_devices() -> None:
	fields = ("voip_token", "voip_token_hash", "voip_enabled", "voip_last_seen_at")
	if not all(frappe.db.has_column(AUTHORIZATION_SOURCE, field) for field in fields):
		return
	for row in frappe.get_all(
		AUTHORIZATION_SOURCE,
		filters={"voip_token": ["is", "set"]},
		fields=["name", "app", "enabled", *fields],
	):
		if not row.app or not row.voip_token:
			continue
		# A token already claimed through the new API wins over legacy ownership.
		existing = frappe.db.exists(VOIP_REGISTRATION_DOCTYPE, registration_name(row.name, row.app))
		claimed = frappe.db.exists(
			VOIP_REGISTRATION_DOCTYPE,
			{"voip_token_hash": hashlib.sha256(row.voip_token.encode()).hexdigest()},
		)
		if not existing and not claimed:
			save_registration(
				row.name,
				row.app,
				row.voip_token,
				int(bool(cint(row.enabled) and cint(row.voip_enabled))),
				row.voip_last_seen_at,
			)
		frappe.db.set_value(
			AUTHORIZATION_SOURCE,
			row.name,
			{"voip_token": None, "voip_token_hash": None, "voip_enabled": 0, "voip_last_seen_at": None},
			update_modified=False,
		)
