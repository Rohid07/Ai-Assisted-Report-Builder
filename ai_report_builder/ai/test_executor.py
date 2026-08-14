"""Phase 1 exit-criteria tests for the run_query executor.

Covers: malformed filters, allow-list rejection, permission-denied,
empty-result, sensitive-field guard, and a real aggregation returning
correct numbers — all through the single permission-safe get_list path.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai.executor import (
    execute_run_query,
    normalize_filters,
    validate_filters,
)

PREFIX = "ZZAITEST"
NOACCESS_USER = "aitest_noaccess@example.com"


class TestRunQueryExecutor(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Three throwaway customers for a deterministic count.
        for i in range(3):
            name = f"{PREFIX} Customer {i}"
            if not frappe.db.exists("Customer", {"customer_name": name}):
                frappe.get_doc(
                    {
                        "doctype": "Customer",
                        "customer_name": name,
                        "customer_group": "Commercial",
                        "territory": "India",
                    }
                ).insert(ignore_permissions=True)
        # A user with no roles → no read on Sales Invoice.
        if not frappe.db.exists("User", NOACCESS_USER):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": NOACCESS_USER,
                    "first_name": "No Access",
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        for c in frappe.get_all(
            "Customer", filters={"customer_name": ("like", f"{PREFIX}%")}
        ):
            frappe.delete_doc("Customer", c.name, force=True, ignore_permissions=True)
        if frappe.db.exists("User", NOACCESS_USER):
            frappe.delete_doc("User", NOACCESS_USER, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def test_malformed_filter_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_filters([["customer_name", "ZZ"]])  # too short

    def test_bad_operator_raises(self):
        with self.assertRaises(frappe.ValidationError):
            validate_filters([["customer_name", "DROP", "x"]])

    def test_normalize_over_nested_filters(self):
        # [[[["f",">",0]]]] -> [["f",">",0]]
        self.assertEqual(
            normalize_filters([[[["outstanding_amount", ">", 0]]]]),
            [["outstanding_amount", ">", 0]],
        )
        # [[c1, c2]] -> [c1, c2]
        self.assertEqual(
            normalize_filters([[["a", "<", 1], ["b", ">", 2]]]),
            [["a", "<", 1], ["b", ">", 2]],
        )
        # already-flat is unchanged
        self.assertEqual(
            normalize_filters([["a", "=", 1]]), [["a", "=", 1]]
        )
        self.assertEqual(normalize_filters([]), [])

    def test_unlisted_doctype_raises(self):
        with self.assertRaises(frappe.ValidationError):
            execute_run_query("User", fields=["name"])  # not on allow-list

    def test_sensitive_field_blocked(self):
        # Customer.tax_id is seeded as sensitive.
        with self.assertRaises(frappe.ValidationError):
            execute_run_query("Customer", fields=["name", "tax_id"])

    def test_unknown_field_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            execute_run_query("Customer", fields=["definitely_not_a_field"])

    def test_empty_result(self):
        res = execute_run_query(
            "Customer",
            fields=["name"],
            filters=[["customer_name", "=", "__no_such_customer__"]],
        )
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["rows"], [])

    def test_order_by_with_direction(self):
        # "field desc" is valid — must not be rejected as an unknown field.
        res = execute_run_query(
            "Customer",
            fields=["name"],
            filters=[["customer_name", "like", f"{PREFIX}%"]],
            order_by="creation desc",
        )
        self.assertEqual(res["count"], 3)

    def test_order_by_bad_field_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            execute_run_query("Customer", fields=["name"], order_by="nope desc")

    def test_aggregation_count_returns_correct_number(self):
        res = execute_run_query(
            "Customer",
            fields=["name"],
            filters=[["customer_name", "like", f"{PREFIX}%"]],
            aggregate_function="count",
        )
        self.assertEqual(res["rows"][0]["_agg"], 3)

    def test_permission_denied(self):
        frappe.set_user(NOACCESS_USER)
        try:
            res = execute_run_query("Sales Invoice", fields=["name"])
            self.assertEqual(res.get("error"), "permission_denied")
        finally:
            frappe.set_user("Administrator")
