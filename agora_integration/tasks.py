import frappe

from agora_integration.services.calls import ACTIVE, expire


def expire_calls() -> None:
	"""Bounded recovery pass; each session is independent and locked before expiry."""
	names = frappe.get_all(
		"Agora Call Session",
		filters={"state": ["in", ACTIVE]},
		pluck="name",
		order_by="modified asc",
		limit=500,
	)
	for name in names:
		call = frappe.get_doc("Agora Call Session", name, for_update=True)
		expire(call)
		frappe.db.commit()
