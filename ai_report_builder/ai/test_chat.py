"""Tests for persistent chat sessions (history + Data/Docs separation)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_report_builder.ai import chat


class TestChatSessions(FrappeTestCase):
    def tearDown(self):
        frappe.db.delete("AI Chat Message", {"content": ("like", "ZZC%")})
        frappe.db.commit()

    def test_save_and_history(self):
        sid = chat.new_session_id()
        chat.save_message(sid, "Data", "user", "ZZC how many customers")
        chat.save_message(sid, "Data", "assistant", "ZZC there are 3")
        hist = chat.session_history(sid)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["role"], "user")
        self.assertEqual(hist[1]["content"], "ZZC there are 3")

    def test_sessions_separated_by_kind(self):
        s_data = chat.new_session_id()
        s_docs = chat.new_session_id()
        chat.save_message(s_data, "Data", "user", "ZZC data question")
        chat.save_message(s_docs, "Docs", "user", "ZZC docs question")

        data_titles = [s.title for s in chat.list_sessions("Data")]
        docs_titles = [s.title for s in chat.list_sessions("Docs")]
        self.assertIn("ZZC data question", data_titles)
        self.assertNotIn("ZZC docs question", data_titles)
        self.assertIn("ZZC docs question", docs_titles)

    def test_get_messages_and_delete(self):
        sid = chat.new_session_id()
        chat.save_message(sid, "Data", "user", "ZZC q1")
        chat.save_message(sid, "Data", "assistant", "ZZC a1",
                          query_params={"doctype": "Customer"}, savable=1)
        msgs = chat.get_session_messages(sid)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[1]["query_params"], {"doctype": "Customer"})
        self.assertEqual(msgs[1]["savable"], 1)

        chat.delete_session(sid)
        self.assertEqual(chat.get_session_messages(sid), [])

    def test_history_capped(self):
        sid = chat.new_session_id()
        for i in range(10):
            chat.save_message(sid, "Data", "user", f"ZZC q{i}")
        self.assertLessEqual(len(chat.session_history(sid)), chat.HISTORY_TURNS)
