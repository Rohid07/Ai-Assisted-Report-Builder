"""Persistent chat sessions (history that survives reloads).

Messages are stored per-user in AI Chat Message, grouped by a `session` id and
separated by `kind` (Data vs Docs) so the how-to docs assistant is its own
thread. All reads are scoped to the current user (owner).
"""

import json

import frappe

HISTORY_TURNS = 6


def new_session_id():
    return frappe.generate_hash(length=12)


def save_message(session, kind, role, content, query_params=None, sources=None, savable=0):
    """Persist one chat message for the current user. Best-effort."""
    try:
        frappe.get_doc(
            {
                "doctype": "AI Chat Message",
                "session": session,
                "kind": kind,
                "role": role,
                "content": content or "",
                "query_params": json.dumps(query_params) if query_params else None,
                "sources": ", ".join(sources) if sources else None,
                "savable": 1 if savable else 0,
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.logger("ai_report_builder").warning("chat save failed")


def session_history(session, limit=HISTORY_TURNS):
    """Prior user/assistant text turns of a session, for LLM context."""
    if not session:
        return []
    rows = frappe.get_all(
        "AI Chat Message",
        filters={"session": session, "owner": frappe.session.user},
        fields=["role", "content"],
        order_by="creation asc",
    )
    turns = [{"role": r.role, "content": r.content} for r in rows if r.content]
    return turns[-limit:]


@frappe.whitelist()
def list_sessions(kind="Data"):
    """Sessions for the current user + kind, newest first, titled by first msg."""
    rows = frappe.db.sql(
        """
        SELECT session,
               MAX(modified) AS last_active,
               SUBSTRING(MIN(CASE WHEN role='user' THEN content END), 1, 80) AS title
        FROM `tabAI Chat Message`
        WHERE owner=%s AND kind=%s
        GROUP BY session
        ORDER BY last_active DESC
        LIMIT 50
        """,
        (frappe.session.user, kind),
        as_dict=True,
    )
    return [r for r in rows if r.title]


@frappe.whitelist()
def get_session_messages(session):
    """All messages of a session (current user), oldest first, for rendering."""
    rows = frappe.get_all(
        "AI Chat Message",
        filters={"session": session, "owner": frappe.session.user},
        fields=["role", "content", "query_params", "sources", "savable"],
        order_by="creation asc",
    )
    for r in rows:
        r["query_params"] = json.loads(r.query_params) if r.get("query_params") else None
    return rows


@frappe.whitelist()
def delete_session(session):
    """Delete all of the current user's messages in a session."""
    frappe.db.delete(
        "AI Chat Message", {"session": session, "owner": frappe.session.user}
    )
    frappe.db.commit()
    return {"ok": True}
