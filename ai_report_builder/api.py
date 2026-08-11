"""Whitelisted endpoints for the chat UI (§7 Phase 3).

The frontend never sees API keys — they are read server-side only inside
answer_question / get_client. Results are capped for the UI (§7: result-table
truncation cap on rows/columns).
"""

import json

import frappe
from openai import APIError

from ai_report_builder.ai.chat import (
    new_session_id,
    save_message,
    session_history,
)
from ai_report_builder.ai.insights import generate_insights
from ai_report_builder.ai.provider import get_client
from ai_report_builder.ai.query import answer_question, audit
from ai_report_builder.ai.rag import answer_doc_question
from ai_report_builder.ai.report import generate_report_metadata, save_as_report

MAX_ROWS = 100
MAX_COLS = 20


def _shape_result(result):
    """Cap rows/columns and derive an ordered column list for the UI table."""
    rows = result.get("rows") or []
    row_truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    columns = []
    for r in rows:
        for k in r.keys():
            if k not in columns:
                columns.append(k)
    col_truncated = len(columns) > MAX_COLS
    if col_truncated:
        columns = columns[:MAX_COLS]
        rows = [{k: r.get(k) for k in columns} for r in rows]

    params = result.get("query_params") or {}
    # §4.8 — grouped/aggregated breakdowns can't be saved as a Report Builder record.
    savable = bool(params) and not params.get("group_by") and not result.get("error")

    return {
        "answer": result.get("answer"),
        "rows": rows,
        "columns": columns,
        "query_params": params,
        "error": result.get("error"),
        "row_truncated": row_truncated,
        "col_truncated": col_truncated,
        "savable": savable,
    }


@frappe.whitelist()
def ask(question, provider=None, session=None):
    """Answer a natural-language question in a persistent chat session.
    Prior turns of the session provide follow-up context (§Phase 5)."""
    if not question or not question.strip():
        frappe.throw(frappe._("Please enter a question."))
    question = question.strip()
    session = session or new_session_id()

    history = session_history(session)
    save_message(session, "Data", "user", question)

    try:
        result = answer_question(question, provider=provider, history=history)
    except APIError:
        # Every configured provider failed (rate limit / quota / dead model).
        result = {
            "answer": frappe._(
                "All configured AI providers are currently unavailable "
                "(rate limit or quota reached). Please wait a few minutes, "
                "switch the Active Provider in AI Assistant Settings, or run "
                "Ollama locally for unlimited use."
            ),
            "rows": [],
            "query_params": {},
            "error": "provider_unavailable",
        }

    shaped = _shape_result(result)
    save_message(
        session, "Data", "assistant", shaped.get("answer"),
        query_params=shaped.get("query_params"), savable=shaped.get("savable"),
    )
    shaped["session"] = session
    return shaped


@frappe.whitelist()
def insights(query_params, question=None):
    """AI summaries & insights over a query's result set (Beyond-MVP #1)."""
    if isinstance(query_params, str):
        query_params = json.loads(query_params)
    try:
        return generate_insights(question, query_params)
    except APIError:
        return {"insights": None, "error": "provider_unavailable"}


@frappe.whitelist()
def ask_docs(question, session=None):
    """Answer a 'how do I...' question from ingested ERPNext docs (RAG, #6),
    in its own persistent Docs session (separate from the Data chat)."""
    if not question or not question.strip():
        frappe.throw(frappe._("Please enter a question."))
    question = question.strip()
    session = session or new_session_id()

    audit("query", question, params={"doctype": "AI Knowledge Chunk"})
    save_message(session, "Docs", "user", question)

    result = answer_doc_question(question)
    save_message(
        session, "Docs", "assistant", result.get("answer"),
        sources=result.get("sources"),
    )
    result["session"] = session
    return result


@frappe.whitelist()
def save_report(query_params, question=None):
    """Save a successful query as a native ERPNext Report Builder record (§4).
    Generates a title/description via the LLM (best-effort), then persists."""
    if isinstance(query_params, str):
        query_params = json.loads(query_params)
    if not query_params or not query_params.get("doctype"):
        frappe.throw(frappe._("Nothing to save — run a query first."))

    name, description = generate_report_metadata(question or "", query_params)
    result = save_as_report(query_params, name, description)
    audit("save", question or "", params={**query_params, "report_name": result["report_name"]})
    return result


@frappe.whitelist()
def test_connection(provider=None):
    """Ping the configured LLM provider so the Settings form can verify keys.
    Never returns the key itself. Returns a clean status instead of a 500."""
    client, model = get_client(provider)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: pong"}],
            max_tokens=5,
        )
    except APIError as e:
        msg = getattr(e, "message", None) or str(e)
        return {"ok": False, "model": model, "error": msg}
    reply = (resp.choices[0].message.content or "").strip()
    return {"ok": True, "model": model, "reply": reply}
