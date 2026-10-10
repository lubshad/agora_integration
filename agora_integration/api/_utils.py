import frappe
from frappe import _


def get_authenticated_user() -> str:
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	return frappe.session.user
