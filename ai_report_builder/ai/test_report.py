"""Phase 4 tests: Save as Report — real Report Builder JSON shape + §4.8 guard."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai.report import save_as_report

PREFIX = "ZZ AI Report"


class TestSaveAsReport(FrappeTestCase):
    @classmethod
    def tearDownClass(cls):
        for r in frappe.get_all("Report", filters={"report_name": ("like", f"{PREFIX}%")}):
            frappe.delete_doc("Report", r.name, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def test_plain_listing_saves_real_shape(self):
        res = save_as_report(
            {
                "doctype": "Sales Invoice",
                "fields": ["name", "customer", "base_grand_total"],
                "filters": [["status", "=", "Unpaid"]],
                "order_by": "posting_date desc",
            },
            f"{PREFIX} Unpaid",
        )
        rep = frappe.get_doc("Report", res["report_name"])
        self.assertEqual(rep.report_type, "Report Builder")
        self.assertEqual(rep.ref_doctype, "Sales Invoice")
        j = json.loads(rep.json)
        # columns are [field, doctype] pairs — the corrected v3 shape
        self.assertEqual(j["columns"][0], ["name", "Sales Invoice"])
        self.assertEqual(j["sort_by"], "Sales Invoice.posting_date")
        self.assertEqual(j["sort_order"], "desc")
        # numeric column present → footer total
        self.assertEqual(j["add_total_row"], 1)
        # filters must be 4-element [doctype, field, op, value] for Report Builder
        self.assertEqual(j["filters"], [["Sales Invoice", "status", "=", "Unpaid"]])
        # it re-runs
        cols, data = rep.get_data(limit=5)[:2]
        self.assertTrue(cols)

    def test_between_filter_saved_four_element(self):
        res = save_as_report(
            {
                "doctype": "Sales Invoice",
                "fields": ["name", "posting_date"],
                "filters": [["posting_date", "between", ["2026-07-01", "2026-07-31"]]],
            },
            f"{PREFIX} Between",
        )
        j = json.loads(frappe.get_doc("Report", res["report_name"]).json)
        self.assertEqual(
            j["filters"],
            [["Sales Invoice", "posting_date", "between", ["2026-07-01", "2026-07-31"]]],
        )

    def test_over_nested_filter_normalized_on_save(self):
        res = save_as_report(
            {"doctype": "Customer", "fields": ["name"],
             "filters": [[["customer_group", "=", "Commercial"]]]},
            f"{PREFIX} Nested",
        )
        j = json.loads(frappe.get_doc("Report", res["report_name"]).json)
        self.assertEqual(j["filters"], [["Customer", "customer_group", "=", "Commercial"]])

    def test_no_numeric_column_no_total_row(self):
        res = save_as_report(
            {"doctype": "Customer", "fields": ["name", "customer_name"]},
            f"{PREFIX} Customers",
        )
        j = json.loads(frappe.get_doc("Report", res["report_name"]).json)
        self.assertEqual(j["add_total_row"], 0)

    def test_grouped_query_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            save_as_report(
                {"doctype": "Sales Invoice", "fields": ["status"], "group_by": "status"},
                f"{PREFIX} Grouped",
            )

    def test_name_collision_gets_suffix(self):
        p = {"doctype": "Customer", "fields": ["name"]}
        a = save_as_report(p, f"{PREFIX} Dup")
        b = save_as_report(p, f"{PREFIX} Dup")
        self.assertNotEqual(a["report_name"], b["report_name"])
        self.assertIn("(2)", b["report_name"])

    def test_sensitive_field_dropped_from_columns(self):
        # Customer.tax_id is seeded sensitive → must not become a column.
        res = save_as_report(
            {"doctype": "Customer", "fields": ["name", "tax_id"]},
            f"{PREFIX} NoPII",
        )
        j = json.loads(frappe.get_doc("Report", res["report_name"]).json)
        self.assertNotIn("tax_id", [c[0] for c in j["columns"]])
