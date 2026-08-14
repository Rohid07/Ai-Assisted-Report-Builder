"""Chat orchestration for the core query loop (§3 steps 3–9, §7 Phase 1).

Ties the LLM tool call to the permission-safe executor. Single-doctype only
in v1 (the model picks the doctype from the schema context).
"""

import json
import re

import frappe
from openai import APIError, BadRequestError

from ai_report_builder.ai.dates import date_context
from ai_report_builder.ai.executor import (
    execute_run_query,
    get_allowed_doctypes,
    get_sensitive_fields,
)
from ai_report_builder.ai.prompts import (
    REFINE_PROMPT,
    RUN_QUERY_TOOL,
    SYSTEM_PROMPT_QUERY,
)
from ai_report_builder.ai.provider import get_provider_chain
from ai_report_builder.ai.router import keyword_route

SCHEMA_CACHE_KEY = "ai_report_builder:schema_context"


def get_schema_context(only=None):
    """Cached wrapper around build_schema_context (§2 step 2 — CACHED).

    `only` scopes the context to a single doctype — a big token saving vs.
    sending every allowed doctype's fields on each call (§Phase 5 token tuning).
    Invalidated when AI Assistant Settings changes (see clear_schema_cache)."""
    key = f"{SCHEMA_CACHE_KEY}:{only or 'all'}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    ctx = build_schema_context(only=only)
    frappe.cache().set_value(key, ctx)
    return ctx


def clear_schema_cache(doc=None, method=None):
    """Hooked to AI Assistant Settings on_update — allow-list / sensitive-field
    changes must rebuild the schema context (all scopes)."""
    frappe.cache().delete_keys(SCHEMA_CACHE_KEY + "*")


def build_schema_context(only=None):
    """Compact, non-sensitive field list per allowed doctype (§2 step 2).
    If `only` is given (and allow-listed), restrict to that one doctype."""
    doctypes = get_allowed_doctypes()
    if only and only in doctypes:
        doctypes = {only}
    lines = []
    for dt in sorted(doctypes):
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
    """§4.7 audit logging — persists an AI Query Log record when enabled.
    Best-effort: a logging failure must never break the actual query."""
    try:
        settings = frappe.get_cached_doc("AI Assistant Settings")
        if not settings.audit_enabled:
            return
        params = params or {}
        frappe.get_doc(
            {
                "doctype": "AI Query Log",
                "action": action,
                "log_user": frappe.session.user,
                "reference_doctype": params.get("doctype") if isinstance(params, dict) else None,
                "question": question,
                "parameters": json.dumps(params, default=str),
                "denial": denial,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.logger("ai_report_builder").warning(
            f"audit failed: {action} / {question}"
        )


class _FakeMsg:
    """Stand-in for a chat message when we recover from a provider error."""

    def __init__(self, content):
        self.content = content
        self.tool_calls = None


def _complete(chain, messages, tools=None):
    """Call the LLM across a provider chain, falling back on rate limits.

    - Groq's 400 `tool_use_failed` (malformed tool call) is recovered as text on
      the same provider — it's not a provider fault, so we don't fall back.
    - Any other provider error (rate limit, quota, dead model, connection)
      advances to the next provider in the chain (§Phase 5).
    Raises the last error if every provider fails."""
    last_error = None
    for client, model, name in chain:
        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        try:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message
        except BadRequestError as e:
            body = getattr(e, "body", None)
            err = body.get("error", {}) if isinstance(body, dict) else {}
            if err.get("code") == "tool_use_failed" and err.get("failed_generation"):
                return _FakeMsg(err["failed_generation"])
            last_error = e  # non-tool-call 400 → treat as provider failure
        except APIError as e:
            last_error = e
        frappe.logger("ai_report_builder").warning(
            f"provider {name} failed: {type(last_error).__name__}"
        )
    raise last_error


def _extract_tool_args(text):
    """Some models (e.g. llama via Groq) occasionally emit the tool call as
    plain text instead of a real tool_call. Recover the params if so."""
    if not text or ("run_query" not in text and '"doctype"' not in text):
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    return data if isinstance(data, dict) and data.get("doctype") else None


def _summarize(rows):
    """Minimal deterministic summary when the model returns no usable prose."""
    if not rows:
        return "No results found."
    if len(rows) == 1 and "_agg" in rows[0]:
        return f"Result: {rows[0]['_agg']}."
    return f"Found {len(rows)} result(s)."


def _safe_execute(question, args):
    """Run execute_run_query, converting any error into a structured result.

    Validation failures use frappe.throw, which queues a user-facing server
    message; since we render our own error in the chat, clear that queue so a
    handled error doesn't also pop a Desk modal."""
    try:
        result = execute_run_query(**args)
    except Exception as e:
        frappe.local.message_log = []  # suppress the leaked frappe.throw modal
        result = {"error": "execution_error", "message": str(e)}
        audit("denied", question, params=args, denial=str(e))
        return result
    if result.get("error"):
        audit("denied", question, params=args, denial=result["error"])
    else:
        audit("query", question, params=args)
    return result


def _run_tool_calls(question, msg, messages):
    """Execute each run_query tool call, append tool results to messages,
    and return (last_result, last_query_params)."""
    messages.append(msg.model_dump(exclude_none=True))
    result, query_params = None, None
    for tc in msg.tool_calls:
        if tc.function.name != "run_query":
            continue
        args = json.loads(tc.function.arguments or "{}")
        query_params = args
        result = _safe_execute(question, args)
        messages.append(
            {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)}
        )
    return result, query_params


HISTORY_TURNS = 6  # cap prior turns fed back (token budget, §Phase 5)


def _clean_history(history):
    """Keep only well-formed user/assistant text turns, most recent HISTORY_TURNS."""
    clean = []
    for m in history or []:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            clean.append({"role": role, "content": content})
    return clean[-HISTORY_TURNS:]


def refine_query(current_params, instruction, provider=None):
    """Modify an existing query per a natural-language instruction. Returns
    {query_params, result, error}. Reuses the constrained run_query tool, so
    the refined query is validated and permission-safe like any other."""
    chain = get_provider_chain(provider)
    doctype = current_params.get("doctype")
    schema_context = get_schema_context(only=doctype) + "\n\n" + date_context()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_QUERY.format(schema_context=schema_context)},
        {
            "role": "user",
            "content": REFINE_PROMPT.format(
                current=json.dumps(current_params), instruction=instruction
            ),
        },
    ]

    for _ in range(2):
        msg = _complete(chain, messages, tools=[RUN_QUERY_TOOL])
        args = None
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name == "run_query":
                    args = json.loads(tc.function.arguments or "{}")
                    break
        if args is None:
            args = _extract_tool_args(msg.content or "")
        if args:
            args["doctype"] = doctype  # never let refinement switch doctype
            result = _safe_execute(instruction, args)
            audit("refine", instruction, params=args,
                  denial=result.get("error") if result else None)
            return {"query_params": args, "result": result, "error": result.get("error")}
        messages.append({"role": "user", "content": "Call the run_query tool with the updated query."})

    return {"query_params": current_params, "result": None, "error": "could_not_refine"}


def answer_question(question, provider=None, history=None, max_tool_rounds=3):
    """Run one question through the LLM + tool loop. Returns a dict with the
    natural-language answer, the raw rows, and the query params used (so the UI
    can offer Save as Report in Phase 4). `history` carries prior chat turns so
    follow-up questions ("what about last month?") keep context (§Phase 5)."""
    chain = get_provider_chain(provider)
    if not chain:
        frappe.throw("No LLM provider is configured. Add an API key in AI Assistant Settings.")

    # Scope the schema to the routed doctype to save prompt tokens; fall back to
    # the full allow-list when routing is uncertain (§Phase 2 router + token tuning).
    routed = keyword_route(question)
    only = routed if routed and routed != "UNKNOWN" else None
    schema_context = get_schema_context(only=only) + "\n\n" + date_context()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_QUERY.format(schema_context=schema_context)},
        *_clean_history(history),
        {"role": "user", "content": question},
    ]

    query_params = None
    result = None

    for _ in range(max_tool_rounds):
        msg = _complete(chain, messages, tools=[RUN_QUERY_TOOL])

        if msg.tool_calls:
            result, query_params = _run_tool_calls(question, msg, messages)
            continue

        # No tool call → a text turn. Recover a tool call emitted as text.
        content = msg.content or ""
        recovered = _extract_tool_args(content)
        if result is None and recovered:
            query_params = recovered
            result = _safe_execute(question, recovered)
            # Loop again so the model can summarize the recovered result.
            messages.append({"role": "user", "content": "Summarize the result in plain business language."})
            continue

        answer = content if content.strip() and not recovered else None
        break
    else:
        # Rounds exhausted while still tool-calling → force a summary with no tools.
        answer = None

    # Force a plain-language summary if we have good data but no prose.
    if not answer and result and not result.get("error"):
        try:
            final = _complete(
                chain,
                messages
                + [{"role": "user", "content": "Give a concise plain-language answer to the question. Do not call any tool."}],
            )
            answer = (final.content or "").strip() or _summarize(result.get("rows"))
        except Exception:
            answer = _summarize(result.get("rows"))

    # Final guards (override any model prose):
    # - errored query → NEVER show model text (it may invent data).
    # - no query at all → guidance to rephrase.
    if result and result.get("error"):
        answer = "I couldn't run that query. Please try rephrasing your question."
    elif result is None and not answer:
        answer = (
            "I can answer questions about your ERPNext data (e.g. sales invoices, "
            "customers, items). I couldn't turn that into a data query — please "
            "try rephrasing."
        )

    audit("answer", question, params=query_params)
    return {
        "answer": answer,
        "rows": result.get("rows") if result else [],
        "query_params": query_params,
        "error": result.get("error") if result else None,
    }
