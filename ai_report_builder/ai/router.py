"""Doctype router — step [1] of the flow (§3, §7 Phase 2).

Classifies which allow-listed doctype a question targets. Two strategies:
  - keyword_route(): free, deterministic, no LLM round-trip (default, cheap).
  - route_doctype(): LLM classifier for when the allow-list grows.

Cost note (§7): a separate router call doubles LLM round-trips per question.
With a small allow-list, prefer keyword routing or letting the main model pick
the doctype from the tool schema.
"""

import frappe

from ai_report_builder.ai.executor import get_allowed_doctypes

# Signals per doctype. Only doctypes on the settings allow-list are ever returned.
KEYWORD_MAP = {
    "Sales Invoice": ["invoice", "sales", "revenue", "billed", "receivable", "paid", "overdue"],
    "Purchase Order": ["purchase", "po ", "supplier order", "procure", "buying", "ordered from"],
    "Customer": ["customer", "client", "buyer", "account"],
    "Item": ["item", "product", "sku", "stock item", "goods"],
    "Supplier": ["supplier", "vendor"],
    "Sales Order": ["sales order", "so "],
}

ROUTER_PROMPT = """You classify which ERPNext doctype a question is about.
Respond with only the doctype name from this list, nothing else:
{doctype_list}.
If none clearly apply, respond: UNKNOWN.

Question: {user_question}"""


def keyword_route(question, allowed=None):
    """Score each allowed doctype by keyword hits; return the best or UNKNOWN."""
    allowed = allowed or get_allowed_doctypes()
    q = f" {question.lower()} "
    best, best_score = "UNKNOWN", 0
    for dt in allowed:
        score = sum(1 for kw in KEYWORD_MAP.get(dt, [dt.lower()]) if kw in q)
        if score > best_score:
            best, best_score = dt, score
    return best


def route_doctype(question, client, model, allowed=None):
    """LLM classifier. Falls back to keyword routing if the answer is not on
    the allow-list."""
    allowed = allowed or get_allowed_doctypes()
    prompt = ROUTER_PROMPT.format(
        doctype_list=", ".join(sorted(allowed)), user_question=question
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
        temperature=0,
    )
    answer = (resp.choices[0].message.content or "").strip()
    if answer in allowed:
        return answer
    return keyword_route(question, allowed)


def check_allowlist(doctype):
    """§4.4 — kept here too for router callers; executor also enforces it."""
    if doctype not in get_allowed_doctypes():
        frappe.throw(f"Doctype '{doctype}' is not enabled for the assistant.")
