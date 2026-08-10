"""Phase 3 tests: result shaping — truncation caps and savable flag (§4.8)."""

from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai.query import _extract_tool_args
from ai_report_builder.api import MAX_COLS, MAX_ROWS, _shape_result


class TestShapeResult(FrappeTestCase):
    def test_row_truncation(self):
        rows = [{"name": f"r{i}"} for i in range(MAX_ROWS + 25)]
        out = _shape_result({"rows": rows, "query_params": {"doctype": "Customer", "fields": ["name"]}})
        self.assertEqual(len(out["rows"]), MAX_ROWS)
        self.assertTrue(out["row_truncated"])

    def test_column_truncation(self):
        wide = {f"c{i}": i for i in range(MAX_COLS + 5)}
        out = _shape_result({"rows": [wide], "query_params": {}})
        self.assertEqual(len(out["columns"]), MAX_COLS)
        self.assertTrue(out["col_truncated"])
        self.assertEqual(len(out["rows"][0]), MAX_COLS)

    def test_columns_derived_in_order(self):
        rows = [{"name": "a", "customer_name": "A"}]
        out = _shape_result({"rows": rows, "query_params": {"doctype": "Customer"}})
        self.assertEqual(out["columns"], ["name", "customer_name"])

    def test_savable_plain_listing(self):
        out = _shape_result(
            {"rows": [{"name": "a"}], "query_params": {"doctype": "Customer", "fields": ["name"]}}
        )
        self.assertTrue(out["savable"])

    def test_not_savable_when_grouped(self):
        out = _shape_result(
            {"rows": [{"_agg": 3}], "query_params": {"doctype": "Customer", "group_by": "customer_group"}}
        )
        self.assertFalse(out["savable"])

    def test_not_savable_on_error(self):
        out = _shape_result(
            {"rows": [], "query_params": {"doctype": "Sales Invoice"}, "error": "permission_denied"}
        )
        self.assertFalse(out["savable"])
        self.assertEqual(out["error"], "permission_denied")

    def test_no_params_not_savable(self):
        out = _shape_result({"rows": [], "query_params": {}})
        self.assertFalse(out["savable"])


class TestToolCallRecovery(FrappeTestCase):
    def test_recovers_from_groq_failed_generation(self):
        # The exact malformed generation Groq returns in tool_use_failed 400s.
        failed = '<function=run_query({"doctype": "Customer", "fields": ["name"]})</function>'
        args = _extract_tool_args(failed)
        self.assertEqual(args["doctype"], "Customer")
        self.assertEqual(args["fields"], ["name"])

    def test_ignores_plain_prose(self):
        self.assertIsNone(_extract_tool_args("There are 6 unpaid invoices."))
