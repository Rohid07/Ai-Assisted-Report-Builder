# Copyright (c) 2026, rohid and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.permissions import (
	get_ai_chat_message_query_conditions,
	get_ai_report_query_conditions,
	has_ai_chat_message_permission,
	has_ai_report_permission,
)

OTHER_USER = "zz_ai_nobody@example.com"


class TestAIReport(FrappeTestCase):
	def test_owner_can_access_own_report(self):
		doc = frappe.new_doc("AI Report")
		doc.owner = OTHER_USER
		self.assertTrue(has_ai_report_permission(doc, "read", OTHER_USER))
		self.assertFalse(has_ai_report_permission(doc, "read", "stranger@example.com"))

	def test_system_manager_sees_everything(self):
		doc = frappe.new_doc("AI Report")
		doc.owner = OTHER_USER
		self.assertTrue(has_ai_report_permission(doc, "read", "Administrator"))

	def test_report_query_conditions_scope_to_owner(self):
		cond = get_ai_report_query_conditions(OTHER_USER)
		self.assertIn("owner", cond)
		self.assertIn(OTHER_USER, cond)
		self.assertEqual(get_ai_report_query_conditions("Administrator"), "")

	def test_chat_message_owner_scoped(self):
		doc = frappe.new_doc("AI Chat Message")
		doc.owner = OTHER_USER
		self.assertTrue(has_ai_chat_message_permission(doc, "read", OTHER_USER))
		self.assertFalse(has_ai_chat_message_permission(doc, "read", "stranger@example.com"))
		cond = get_ai_chat_message_query_conditions(OTHER_USER)
		self.assertIn("owner", cond)
		self.assertIn(OTHER_USER, cond)
