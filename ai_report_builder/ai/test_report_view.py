"""Tests for the custom formatted report view (save + run payload)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai.report_view import run_ai_report, save_ai_report

PREFIX = "ZZRV"


class TestReportView(FrappeTestCase):
    @classmethod
    def tearDownClass(cls):
        for r in frappe.get_all("AI Report", filters={"report_title": ("like", f"{PREFIX}%")}):
            frappe.delete_doc("AI Report", r.name, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def _save(self, params, q):
        # native=False so tests don't create native Report twins to clean up.
        params = dict(params)
        res = save_ai_report(params, question=q, native=False)
        doc = frappe.get_doc("AI Report", res["name"])
        doc.db_set("report_title", f"{PREFIX} {res['name'][-4:]}")
        return res["name"]

    def test_listing_run_has_columns_and_totals(self):
        name = self._save(
            {"doctype": "Sales Invoice", "fields": ["name", "customer", "base_grand_total"],
             "filters": [["status", "in", ["Unpaid", "Overdue"]]]},
            "unpaid invoices",
        )
        out = run_ai_report(name)
        self.assertIsNone(out["error"])
        labels = [c["label"] for c in out["columns"]]
        self.assertIn("Customer", labels)  # human label, not fieldname
        # base_grand_total is Currency → included in totals
        self.assertIn("base_grand_total", out["totals"])
        self.assertGreater(out["totals"]["base_grand_total"], 0)

    def test_aggregate_run_builds_chart(self):
        name = self._save(
            {"doctype": "Sales Invoice", "fields": ["status"],
             "aggregate_function": "count", "group_by": "status"},
            "count by status",
        )
        out = run_ai_report(name)
        self.assertIsNone(out["error"])
        self.assertIsNotNone(out["chart"])
        self.assertEqual(len(out["chart"]["labels"]), len(out["chart"]["values"]))
        # aggregate column labelled "Count"
        self.assertIn("Count", [c["label"] for c in out["columns"]])

    def test_kind_recorded(self):
        n1 = self._save({"doctype": "Customer", "fields": ["name"]}, "customers")
        n2 = self._save({"doctype": "Customer", "fields": ["name"],
                         "aggregate_function": "count"}, "count customers")
        self.assertEqual(frappe.db.get_value("AI Report", n1, "report_kind"), "Listing")
        self.assertEqual(frappe.db.get_value("AI Report", n2, "report_kind"), "Aggregate")
