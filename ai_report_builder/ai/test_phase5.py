"""Phase 5 tests: audit log persistence, conversation history, and proof that
the aggregate get_list path respects User Permissions (the §4.2 hole)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai.executor import execute_run_query
from ai_report_builder.ai.query import _clean_history, audit

PREFIX = "ZZ5"
LIMITED_USER = "aitest_limited@example.com"


class TestAudit(FrappeTestCase):
    def setUp(self):
        self.settings = frappe.get_single("AI Assistant Settings")
        self._orig = self.settings.audit_enabled

    def tearDown(self):
        self.settings.db_set("audit_enabled", self._orig)
        frappe.db.delete("AI Query Log", {"question": ("like", f"{PREFIX}%")})
        frappe.db.commit()

    def test_audit_creates_log(self):
        self.settings.db_set("audit_enabled", 1)
        audit("query", f"{PREFIX} how many customers", params={"doctype": "Customer"})
        rows = frappe.get_all(
            "AI Query Log",
            filters={"question": f"{PREFIX} how many customers"},
            fields=["action", "reference_doctype", "log_user"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, "query")
        self.assertEqual(rows[0].reference_doctype, "Customer")

    def test_audit_respects_toggle(self):
        self.settings.db_set("audit_enabled", 0)
        audit("query", f"{PREFIX} disabled", params={"doctype": "Customer"})
        self.assertEqual(
            frappe.db.count("AI Query Log", {"question": f"{PREFIX} disabled"}), 0
        )

    def test_audit_never_raises(self):
        self.settings.db_set("audit_enabled", 1)
        # Bad params must not blow up the caller.
        audit("save", f"{PREFIX} weird", params={"doctype": "Customer", "x": object()})


class TestHistory(FrappeTestCase):
    def test_clean_history_filters_and_caps(self):
        raw = [{"role": "system", "content": "x"}] + [
            {"role": "user", "content": f"q{i}"} for i in range(10)
        ] + [{"role": "assistant", "content": ""}, {"role": "user", "content": None}]
        out = _clean_history(raw)
        self.assertLessEqual(len(out), 6)
        self.assertTrue(all(m["role"] in ("user", "assistant") for m in out))
        self.assertTrue(all(m["content"] for m in out))


class TestUserPermissionIsolation(FrappeTestCase):
    """§4.2: aggregation goes through get_list, which enforces User Permissions.
    A restricted user must not aggregate across records they cannot see."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cust_a = cls._make_customer(f"{PREFIX} Cust A")
        cls.cust_b = cls._make_customer(f"{PREFIX} Cust B")
        if not frappe.db.exists("User", LIMITED_USER):
            u = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": LIMITED_USER,
                    "first_name": "Limited",
                    "send_welcome_email": 0,
                    "roles": [{"role": "Sales User"}],
                }
            )
            u.insert(ignore_permissions=True)
        # Restrict the user to Cust A only.
        if not frappe.db.exists(
            "User Permission", {"user": LIMITED_USER, "allow": "Customer", "for_value": cls.cust_a}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": LIMITED_USER,
                    "allow": "Customer",
                    "for_value": cls.cust_a,
                }
            ).insert(ignore_permissions=True)
        frappe.db.commit()

    @staticmethod
    def _make_customer(name):
        if not frappe.db.exists("Customer", {"customer_name": name}):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": name,
                    "customer_group": "Commercial",
                    "territory": "India",
                }
            ).insert(ignore_permissions=True)
        return frappe.db.get_value("Customer", {"customer_name": name}, "name")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission", {"user": LIMITED_USER})
        for n in (cls.cust_a, cls.cust_b):
            if n:
                frappe.delete_doc("Customer", n, force=True, ignore_permissions=True)
        if frappe.db.exists("User", LIMITED_USER):
            frappe.delete_doc("User", LIMITED_USER, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def test_restricted_user_aggregate_does_not_leak(self):
        # As Administrator, both customers are countable.
        admin = execute_run_query(
            "Customer",
            fields=["name"],
            filters=[["customer_name", "like", f"{PREFIX}%"]],
            aggregate_function="count",
        )
        self.assertEqual(admin["rows"][0]["_agg"], 2)

        # As the restricted user, the aggregate must see only Cust A (not B).
        frappe.set_user(LIMITED_USER)
        try:
            restricted = execute_run_query(
                "Customer", fields=["name"], aggregate_function="count"
            )
            self.assertEqual(
                restricted["rows"][0]["_agg"], 1,
                "aggregation leaked records the user cannot see — §4.2 hole!",
            )
        finally:
            frappe.set_user("Administrator")
