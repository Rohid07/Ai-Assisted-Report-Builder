"""Save a successful query as a native ERPNext Report Builder record
(§7 Phase 4 — the core differentiator).

The JSON shape is the real v15 Report Builder shape (bench-verified in Phase 0.5):
columns are [fieldname, source_doctype] pairs under `columns`, sorting uses
`sort_by: "Doctype.field"` + `sort_order`, and `add_total_row` gives a free
footer sum. Report Builder cannot GROUP BY (§4.8) — grouped queries are rejected.
"""

import json
import re

import frappe

from ai_report_builder.ai.executor import _valid_fieldnames, get_sensitive_fields
from ai_report_builder.ai.prompts import REPORT_METADATA_PROMPT
from ai_report_builder.ai.provider import get_provider_chain

NUMERIC_TYPES = {"Currency", "Float", "Int"}


def _fallback_name(query_params, question):
    base = (question or "").strip()
    if base:
        return base[:60]
    return f"{query_params.get('doctype', 'Data')} report"


def generate_report_metadata(question, query_params, provider=None):
    """LLM-generated title + description, with a deterministic fallback."""
    from ai_report_builder.ai.query import _complete  # avoid circular import

    prompt = REPORT_METADATA_PROMPT.format(
        question=question,
        doctype=query_params.get("doctype"),
        filters=query_params.get("filters"),
        fields=query_params.get("fields"),
        group_by=query_params.get("group_by"),
        order_by=query_params.get("order_by"),
    )
    try:
        chain = get_provider_chain(provider)
        msg = _complete(chain, [{"role": "user", "content": prompt}])
        m = re.search(r"\{.*\}", msg.content or "", re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
        name = (data.get("report_name") or "").strip()
        desc = (data.get("description") or "").strip()
        if name:
            return name, desc
    except Exception:
        pass
    return _fallback_name(query_params, question), ""


def _report_columns(query_params, ref_doctype):
    """Plain, valid, non-sensitive fieldnames as [field, doctype] pairs.
    Includes the aggregate_field for a single-column total (§4.8)."""
    valid = _valid_fieldnames(ref_doctype)
    sensitive = get_sensitive_fields(ref_doctype)

    names = list(query_params.get("fields") or [])
    agg_field = query_params.get("aggregate_field")
    if agg_field and agg_field not in names:
        names.append(agg_field)

    cols = []
    for f in names:
        fieldname = str(f).split(".")[0].split()[0]
        if fieldname in valid and fieldname not in sensitive and fieldname not in [c[0] for c in cols]:
            cols.append([fieldname, ref_doctype])
    return cols or [["name", ref_doctype]]


def save_as_report(query_params, report_name, description=""):
    """Create a native Report Builder record from query params."""
    if not frappe.has_permission("Report", "create"):
        frappe.throw("You don't have permission to create reports.")

    ref_doctype = query_params["doctype"]

    # GUARD (§4.8): Report Builder cannot GROUP BY. A grouped/aggregated
    # breakdown is not savable — the UI hides the button; enforce it here too.
    if query_params.get("group_by"):
        frappe.throw(
            "Grouped breakdowns can't be saved as a native report — "
            "export the result instead."
        )

    columns = _report_columns(query_params, ref_doctype)

    # order_by "field asc" → sort_by "Doctype.field" + sort_order.
    sort_by, sort_order = f"{ref_doctype}.modified", "desc"
    if query_params.get("order_by"):
        parts = query_params["order_by"].split()
        sort_by = f"{ref_doctype}.{parts[0]}"
        sort_order = parts[1].lower() if len(parts) > 1 and parts[1].lower() in ("asc", "desc") else "asc"

    # add_total_row: 1 gives a free footer sum when any numeric column is present.
    meta = frappe.get_meta(ref_doctype)
    has_numeric = any(
        (meta.get_field(c[0]) and meta.get_field(c[0]).fieldtype in NUMERIC_TYPES)
        for c in columns
    )

    builder_json = {
        "add_total_row": 1 if has_numeric else 0,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "sort_by_next": None,
        "sort_order_next": "desc",
        "filters": query_params.get("filters", []),
        "columns": columns,
    }

    # Report is named by report_name — make it unique.
    base, name, n = report_name, report_name, 2
    while frappe.db.exists("Report", name):
        name = f"{base} ({n})"
        n += 1

    report = frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": name,
            "ref_doctype": ref_doctype,
            "report_type": "Report Builder",
            "is_standard": "No",
            "json": json.dumps(builder_json),
        }
    )
    report.insert()

    return {
        "report_name": report.name,
        "url": f"/app/report/{report.name}",
        "description": description,
    }
