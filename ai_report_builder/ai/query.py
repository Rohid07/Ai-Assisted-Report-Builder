"""Chat orchestration for the core query loop (§3 steps 3–9, §7 Phase 1).

Ties the LLM tool call to the permission-safe executor. Single-doctype only
in v1 (the model picks the doctype from the schema context).
"""

import json

import frappe

from ai_report_builder.ai.executor import (
    execute_run_query,
    get_allowed_doctypes,
    get_sensitive_fields,
)
from ai_report_builder.ai.prompts import RUN_QUERY_TOOL, SYSTEM_PROMPT_QUERY
from ai_report_builder.ai.provider import get_client


def build_schema_context():
    """Compact, non-sensitive field list per allowed doctype (§2 step 2).
    Cached in Phase 2; built inline here."""
    lines = []
    for dt in sorted(get_allowed_doctypes()):
        if not frappe.db.exists("DocType", dt):
            continue
        meta = frappe.get_meta(dt)
        sensitive = get_sensitive_fields(dt)
        fields = []
        for df in meta.get("fields"):
            if not df.fieldname or df.fieldname in sensitive:
                continue
            if df.fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML"):
                continue
            fields.append(f"{df.fieldname} ({df.fieldtype})")
        lines.append(f"- {dt}: " + ", ".join(fields[:40]))
    return "\n".join(lines)


def audit(action, question, params=None, denial=None):
    """§4.7 audit logging. Minimal logger sink for Phase 1; a dedicated
    AI Query Log doctype arrives in a later phase."""
    settings = frappe.get_single("AI Assistant Settings")
    if not settings.audit_enabled:
        return
    entry = {
        "user": frappe.session.user,
        "action": action,
        "question": question,
        "params": params,
        "denial": denial,
    }
    frappe.logger("ai_report_builder").info(json.dumps(entry, default=str))


def answer_question(question, provider=None, max_tool_rounds=1):
    """Run one question through the LLM + tool loop. Returns a dict with the
    natural-language answer, the raw rows, and the query params used (so the UI
    can offer Save as Report in Phase 4)."""
    client, model = get_client(provider)
    schema_context = build_schema_context()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_QUERY.format(schema_context=schema_context)},
        {"role": "user", "content": question},
    ]

    query_params = None
    result = None

    for _ in range(max_tool_rounds + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[RUN_QUERY_TOOL],
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            audit("answer", question, params=query_params)
            return {
                "answer": msg.content,
                "rows": result.get("rows") if result else [],
                "query_params": query_params,
            }

        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            if tc.function.name != "run_query":
                continue
            args = json.loads(tc.function.arguments or "{}")
            query_params = args
            try:
                result = execute_run_query(**args)
            except Exception as e:
                result = {"error": "execution_error", "message": str(e)}
                audit("denied", question, params=args, denial=str(e))
            else:
                if result.get("error"):
                    audit("denied", question, params=args, denial=result["error"])
                else:
                    audit("query", question, params=args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    # Fell through the loop without a final text answer — summarize what we have.
    return {
        "answer": None,
        "rows": result.get("rows") if result else [],
        "query_params": query_params,
    }
