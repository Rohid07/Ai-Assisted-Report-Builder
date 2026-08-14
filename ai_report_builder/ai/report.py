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

from ai_report_builder.ai.executor import (
    _valid_fieldnames,
    get_sensitive_fields,
    normalize_filters,
)
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


def _report_filters(filters, ref_doctype):
    """Report Builder stores filters as [doctype, field, operator, value] — 4
    elements. get_list filters are usually [field, op, value] (3). Convert so
    saved reports actually apply the filter instead of showing every row."""
    out = []
    for f in normalize_filters(filters) or []:
        if not isinstance(f, (list, tuple)):
            continue
        if len(f) == 4:
            out.append([f[0], f[1], f[2], f[3]])
        elif len(f) == 3:
            out.append([ref_doctype, f[0], f[1], f[2]])
    return out


# Curated display columns per doctype — used to enrich a sparse query so the
# saved native report shows meaningful columns, not just the 1-2 the model picked.
DEFAULT_REPORT_COLUMNS = {
    "Sales Invoice": ["name", "customer", "posting_date", "due_date", "status",
                      "grand_total", "outstanding_amount"],
    "Purchase Order": ["name", "supplier", "transaction_date", "status",
                       "grand_total", "per_received"],
    "Customer": ["name", "customer_name", "customer_group", "territory",
                 "customer_type"],
    "Item": ["name", "item_name", "item_group", "stock_uom", "standard_rate"],
}
MAX_REPORT_COLUMNS = 8


def _report_columns(query_params, ref_doctype):
    """Build meaningful [field, doctype] columns: the fields the model chose,
    enriched with curated defaults for the doctype. Valid + non-sensitive."""
    valid = _valid_fieldnames(ref_doctype)
    sensitive = get_sensitive_fields(ref_doctype)

    ordered = list(query_params.get("fields") or [])
    agg_field = query_params.get("aggregate_field")
    if agg_field and agg_field not in ordered:
        ordered.append(agg_field)
    # Enrich sparse listings with curated defaults (skip for aggregate saves).
    if not query_params.get("aggregate_function"):
        ordered += DEFAULT_REPORT_COLUMNS.get(ref_doctype, [])

    cols, seen = [], set()
    for f in ordered:
        fieldname = str(f).split(".")[0].split()[0]
        if (
            fieldname in valid
            and fieldname not in sensitive
            and fieldname not in seen
        ):
            cols.append([fieldname, ref_doctype])
            seen.add(fieldname)
        if len(cols) >= MAX_REPORT_COLUMNS:
            break
    return cols or [["name", ref_doctype]]


def _build_builder_json(query_params, ref_doctype):
    """The real v15 Report Builder JSON (columns as [field, doctype] pairs,
    4-element filters, sort keys, total row for numeric columns)."""
    columns = _report_columns(query_params, ref_doctype)

    sort_by, sort_order = f"{ref_doctype}.modified", "desc"
    if query_params.get("order_by"):
        parts = query_params["order_by"].split()
        sort_by = f"{ref_doctype}.{parts[0]}"
        sort_order = parts[1].lower() if len(parts) > 1 and parts[1].lower() in ("asc", "desc") else "asc"

    meta = frappe.get_meta(ref_doctype)
    has_numeric = any(
        (meta.get_field(c[0]) and meta.get_field(c[0]).fieldtype in NUMERIC_TYPES)
        for c in columns
    )
    return {
        "add_total_row": 1 if has_numeric else 0,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "sort_by_next": None,
        "sort_order_next": "desc",
        "filters": _report_filters(query_params.get("filters"), ref_doctype),
        "columns": columns,
    }


def save_as_report(query_params, report_name, description=""):
    """Create a native Report Builder record from query params."""
    if not frappe.has_permission("Report", "create"):
        frappe.throw("You don't have permission to create reports.")

    ref_doctype = query_params["doctype"]

    # GUARD (§4.8): Report Builder cannot GROUP BY.
    if query_params.get("group_by"):
        frappe.throw(
            "Grouped breakdowns can't be saved as a native report — "
            "export the result instead."
        )

    builder_json = _build_builder_json(query_params, ref_doctype)

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


def update_native_report(report_name, query_params):
    """Rebuild an existing native Report's JSON from (refined) query params.
    Skips silently if the report is gone or the query became grouped."""
    if not report_name or not frappe.db.exists("Report", report_name):
        return False
    if query_params.get("group_by"):
        return False  # native Report Builder can't group
    try:
        builder_json = _build_builder_json(query_params, query_params["doctype"])
        frappe.db.set_value("Report", report_name, "json", json.dumps(builder_json))
        return True
    except Exception:
        frappe.logger("ai_report_builder").warning("native report update failed")
        return False
