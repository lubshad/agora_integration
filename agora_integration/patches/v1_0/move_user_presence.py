"""Move the User presence fields from sync_dating to agora_integration.

Creates ``User.agora_presence`` / ``User.agora_last_seen``, copies any values
recorded under the legacy ``sync_presence`` / ``sync_last_seen`` fields, then
removes the legacy custom fields. Safe on fresh installs where the legacy
fields never existed.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

LEGACY_FIELDS = ("sync_presence", "sync_last_seen")


def execute() -> None:
	create_custom_fields(_custom_fields())
	# Snapshot columns directly: deleting a Custom Field clears the doctype
	# cache, which makes frappe.db.has_column unreliable mid-patch.
	columns = _user_columns()
	_copy_legacy_values(columns)
	_drop_legacy_fields(columns)


def _custom_fields() -> dict:
	return {
		"User": [
			{
				"fieldname": "agora_presence",
				"label": "Agora Presence",
				"fieldtype": "Select",
				"options": "Foreground\nBackground\nOffline",
				"default": "Offline",
				"read_only": 1,
				"in_list_view": 1,
				"insert_after": "last_login",
				"module": "Agora Integration",
			},
			{
				"fieldname": "agora_last_seen",
				"label": "Agora Last Seen",
				"fieldtype": "Datetime",
				"read_only": 1,
				"insert_after": "agora_presence",
				"module": "Agora Integration",
			},
		]
	}


def _user_columns() -> set[str]:
	rows = frappe.db.sql("SHOW COLUMNS FROM `tabUser`", as_dict=True)
	return {row["Field"] for row in rows}


def _copy_legacy_values(columns: set[str]) -> None:
	pairs = [
		f"`agora_{legacy.removeprefix('sync_')}` = `{legacy}`"
		for legacy in LEGACY_FIELDS
		if legacy in columns
	]
	if not pairs:
		return
	frappe.db.sql(f"UPDATE `tabUser` SET {', '.join(pairs)}")
	frappe.db.commit()


def _drop_legacy_fields(columns: set[str]) -> None:
	for legacy in LEGACY_FIELDS:
		name = f"User-{legacy}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
			frappe.db.commit()
		if legacy in columns:
			frappe.db.sql_ddl(f"ALTER TABLE `tabUser` DROP COLUMN `{legacy}`")
	frappe.db.commit()
