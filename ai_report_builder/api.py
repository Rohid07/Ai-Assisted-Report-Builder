"""Whitelisted endpoints for the chat UI (§7 Phase 3).

The frontend never sees API keys — they are read server-side only inside
answer_question / get_client. Results are capped for the UI (§7: result-table
truncation cap on rows/columns).
"""

import frappe
from openai import APIError

from ai_report_builder.ai.provider import get_client
from ai_report_builder.ai.query import answer_question

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
def ask(question, provider=None):
    """Answer a natural-language question. Returns shaped, capped results."""
    if not question or not question.strip():
        frappe.throw(frappe._("Please enter a question."))
    try:
        result = answer_question(question.strip(), provider=provider)
    except APIError:
        # Every configured provider failed (rate limit / quota / dead model).
        # Fail soft with guidance instead of a 500 (§Phase 5).
        return _shape_result(
            {
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
        )
    return _shape_result(result)


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
