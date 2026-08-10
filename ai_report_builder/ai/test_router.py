"""Phase 2 tests: keyword routing accuracy, date resolution, schema cache."""

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai.dates import date_context, resolve_date_phrase
from ai_report_builder.ai.query import (
    SCHEMA_CACHE_KEY,
    clear_schema_cache,
    get_schema_context,
)
from ai_report_builder.ai.router import keyword_route

ALLOWED = {"Sales Invoice", "Purchase Order", "Customer", "Item"}

# (question, expected doctype)
ROUTE_CASES = [
    ("How many customers do we have?", "Customer"),
    ("List all clients in Mumbai", "Customer"),
    ("Total revenue from sales invoices last month", "Sales Invoice"),
    ("Show unpaid invoices", "Sales Invoice"),
    ("Which items are low on stock?", "Item"),
    ("List all products", "Item"),
    ("Purchase orders raised this quarter", "Purchase Order"),
    ("What did we procure last year?", "Purchase Order"),
    ("Show overdue invoices", "Sales Invoice"),
    ("Count of buyers by group", "Customer"),
]


class TestRouter(FrappeTestCase):
    def test_keyword_routing_accuracy(self):
        correct = sum(
            1 for q, exp in ROUTE_CASES if keyword_route(q, ALLOWED) == exp
        )
        accuracy = correct / len(ROUTE_CASES)
        self.assertGreaterEqual(accuracy, 0.9, f"routing accuracy {accuracy:.0%}")

    def test_unknown_when_no_signal(self):
        self.assertEqual(keyword_route("What is the weather?", ALLOWED), "UNKNOWN")


class TestDates(FrappeTestCase):
    TODAY = "2026-08-10"  # a Monday

    def test_today_yesterday(self):
        self.assertEqual(
            resolve_date_phrase("today", self.TODAY),
            (frappe.utils.getdate("2026-08-10"), frappe.utils.getdate("2026-08-10")),
        )
        self.assertEqual(
            resolve_date_phrase("yesterday", self.TODAY),
            (frappe.utils.getdate("2026-08-09"), frappe.utils.getdate("2026-08-09")),
        )

    def test_last_month(self):
        f, t = resolve_date_phrase("last month", self.TODAY)
        self.assertEqual((f.isoformat(), t.isoformat()), ("2026-07-01", "2026-07-31"))

    def test_this_month(self):
        f, t = resolve_date_phrase("this month", self.TODAY)
        self.assertEqual((f.isoformat(), t.isoformat()), ("2026-08-01", "2026-08-31"))

    def test_quarters(self):
        f, t = resolve_date_phrase("q1", self.TODAY)
        self.assertEqual((f.isoformat(), t.isoformat()), ("2026-01-01", "2026-03-31"))
        f, t = resolve_date_phrase("this quarter", self.TODAY)  # Aug -> Q3
        self.assertEqual((f.isoformat(), t.isoformat()), ("2026-07-01", "2026-09-30"))
        f, t = resolve_date_phrase("last quarter", self.TODAY)  # Q2
        self.assertEqual((f.isoformat(), t.isoformat()), ("2026-04-01", "2026-06-30"))

    def test_last_year(self):
        f, t = resolve_date_phrase("last year", self.TODAY)
        self.assertEqual((f.isoformat(), t.isoformat()), ("2025-01-01", "2025-12-31"))

    def test_last_n_days(self):
        f, t = resolve_date_phrase("last 7 days", self.TODAY)
        self.assertEqual((f.isoformat(), t.isoformat()), ("2026-08-03", "2026-08-10"))

    def test_unrecognized(self):
        self.assertIsNone(resolve_date_phrase("sometime soon", self.TODAY))

    def test_date_context_has_today(self):
        self.assertIn("2026-08-10", date_context(self.TODAY))


class TestSchemaCache(FrappeTestCase):
    def test_cache_populates_and_clears(self):
        key = f"{SCHEMA_CACHE_KEY}:all"
        clear_schema_cache()
        self.assertIsNone(frappe.cache().get_value(key))
        ctx = get_schema_context()
        self.assertTrue(ctx)
        self.assertEqual(frappe.cache().get_value(key), ctx)
        clear_schema_cache()
        self.assertIsNone(frappe.cache().get_value(key))

    def test_scoped_context_is_smaller(self):
        full = get_schema_context()
        scoped = get_schema_context(only="Customer")
        self.assertIn("Customer", scoped)
        self.assertNotIn("Sales Invoice", scoped)
        self.assertLessEqual(len(scoped), len(full))
