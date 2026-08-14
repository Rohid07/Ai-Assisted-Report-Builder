"""Beyond-MVP tests: RAG retrieval/chunking and insights grounding."""

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai import rag
from ai_report_builder.ai.insights import generate_insights

PREFIX = "ZZKB"


class TestRagChunking(FrappeTestCase):
    def test_chunk_splits_on_paragraphs(self):
        content = ("A " * 200) + "\n\n" + ("B " * 200)
        chunks = rag._chunk(content)
        self.assertGreaterEqual(len(chunks), 2)

    def test_chunk_short_content_single(self):
        self.assertEqual(len(rag._chunk("just one line")), 1)

    def test_keyword_score_ranks_overlap(self):
        s_hit = rag._keyword_score("schedule report email", "schedule a report by email")
        s_miss = rag._keyword_score("schedule report email", "creating a customer record")
        self.assertGreater(s_hit, s_miss)


class TestRagRetrieval(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Insert chunks with NO embedding → exercises the keyword fallback path.
        cls.docs = [
            (f"{PREFIX} Scheduling reports by email", "Use Auto Email Report to schedule and email a report."),
            (f"{PREFIX} Creating a customer", "Go to Customer and click New to create a customer."),
        ]
        for title, content in cls.docs:
            frappe.get_doc(
                {"doctype": "AI Knowledge Chunk", "title": title, "source": "test",
                 "content": content}
            ).insert(ignore_permissions=True)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        for c in frappe.get_all("AI Knowledge Chunk", filters={"title": ("like", f"{PREFIX}%")}):
            frappe.delete_doc("AI Knowledge Chunk", c.name, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def test_retrieve_ranks_relevant_first(self):
        hits = rag.retrieve("how do I email a report on a schedule?", k=2)
        self.assertTrue(hits)
        self.assertIn("Scheduling", hits[0].title)


class TestInsightsGuard(FrappeTestCase):
    def test_no_query_returns_error(self):
        self.assertEqual(generate_insights("x", {})["error"], "no_query")

    def test_empty_rows_message(self):
        res = generate_insights(
            "none",
            {"doctype": "Customer", "fields": ["name"],
             "filters": [["customer_name", "=", "__nope__"]]},
        )
        self.assertIsNone(res["error"])
        self.assertIn("No data", res["insights"])
