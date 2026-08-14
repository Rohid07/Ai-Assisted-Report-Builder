"""AI summaries & insights over a result set (Beyond-MVP roadmap #1).

Re-runs the (already validated) query to get fresh, permission-safe rows, then
asks the LLM for concrete, grounded insights. Never invents numbers — the prompt
and the "only use provided data" rule keep it anchored to real rows.
"""

import json

import frappe

from ai_report_builder.ai.executor import execute_run_query
from ai_report_builder.ai.prompts import INSIGHTS_PROMPT

INSIGHT_ROW_CAP = 100  # rows fed to the model


def generate_insights(question, query_params, provider=None):
    """Return {"insights": text, "error": ...}. Grounded in real query rows."""
    from ai_report_builder.ai.query import _complete
    from ai_report_builder.ai.provider import get_provider_chain

    if not query_params or not query_params.get("doctype"):
        return {"insights": None, "error": "no_query"}

    # Re-run through the same permission-safe path; cap rows for the prompt.
    params = dict(query_params)
    params["limit"] = INSIGHT_ROW_CAP
    result = execute_run_query(**params)
    if result.get("error"):
        return {"insights": None, "error": result["error"]}

    rows = result.get("rows") or []
    if not rows:
        return {"insights": "No data to analyse.", "error": None}

    prompt = INSIGHTS_PROMPT.format(
        question=question or "",
        row_count=len(rows),
        rows=json.dumps(rows, default=str)[:6000],
    )
    try:
        chain = get_provider_chain(provider)
        msg = _complete(chain, [{"role": "user", "content": prompt}])
        text = (msg.content or "").strip()
        return {"insights": text or None, "error": None}
    except Exception:
        frappe.logger("ai_report_builder").warning("insights generation failed")
        return {"insights": None, "error": "provider_unavailable"}
