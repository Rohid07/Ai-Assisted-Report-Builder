"""Owner-scoped permissions for user-generated records.

Business users own their saved reports and chat messages; a record is only
visible/touchable by its owner, while System Manager sees everything. These
hooks back the doctype-level grants: roles open the door, this closes it to
the owner's own rows (list view via query conditions, detail via has_permission).
"""

import frappe


def _is_system_manager(user):
	return "System Manager" in frappe.get_roles(user)


def has_ai_report_permission(doc=None, ptype="read", user=None, debug=None):
	"""AI Report: only the owner (or System Manager) may touch a record."""
	user = user or frappe.session.user
	if not doc or _is_system_manager(user):
		return True  # doctype-level check; query conditions scope the list
	return doc.owner == user


def get_ai_report_query_conditions(user, doctype=None):
	"""List view: non-admins only ever see their own reports."""
	user = user or frappe.session.user
	if _is_system_manager(user):
		return ""
	return f"(`owner` = {frappe.db.escape(user)})"


def has_ai_chat_message_permission(doc=None, ptype="read", user=None, debug=None):
	"""AI Chat Message: sessions are private to their owner."""
	user = user or frappe.session.user
	if not doc or _is_system_manager(user):
		return True
	return doc.owner == user


def get_ai_chat_message_query_conditions(user, doctype=None):
	user = user or frappe.session.user
	if _is_system_manager(user):
		return ""
	return f"(`owner` = {frappe.db.escape(user)})"
