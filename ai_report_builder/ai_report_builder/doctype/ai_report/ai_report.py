# Copyright (c) 2026, rohid and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIReport(Document):
	def has_permission(self, ptype="read", user=None):
		"""Owner-scoped: a user may only touch their own reports."""
		user = user or frappe.session.user
		if "System Manager" in frappe.get_roles(user):
			return True
		return self.owner == user

	def get_permission_query_conditions(self, user=None):
		user = user or frappe.session.user
		if "System Manager" in frappe.get_roles(user):
			return ""
		return f"(owner = {frappe.db.escape(user)})"
