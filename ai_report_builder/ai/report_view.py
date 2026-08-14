"""Custom formatted report: save a query as an AI Report and render it on a
dedicated, polished page (not the plain doctype list view).

Unlike the native Report Builder path, this re-runs the saved query through the
permission-safe executor on every view (always live) and supports grouped /
aggregate reports with a chart.
"""

import json

import frappe

from ai_report_builder.ai.executor import execute_run_query
from ai_report_builder.ai.report import generate_report_metadata, save_as_report

NUMERIC_TYPES = {"Currency", "Float", "Int", "Percent"}
_AGG_LABEL = {"sum": "Total", "avg": "Average", "count": "Count"}


@frappe.whitelist()
def save_ai_report(query_params, question=None, native=True):
    """Persist an AI Report definition (and a native ERPNext Report twin for
    listings). Returns {name, url, native_report, native_url}."""
    if isinstance(query_params, str):
        query_params = json.loads(query_params)
    native = frappe.utils.cint(native) if isinstance(native, str) else bool(native)
    if not query_params or not query_params.get("doctype"):
        frappe.throw(frappe._("Nothing to save — run a query first."))

    title, description = generate_report_metadata(question or "", query_params)
    is_agg = bool(query_params.get("group_by") or query_params.get("aggregate_function"))

    doc = frappe.get_doc(
        {
            "doctype": "AI Report",
            "report_title": title,
            "reference_doctype": query_params["doctype"],
            "report_kind": "Aggregate" if is_agg else "Listing",
            "description": description,
            "question": question,
            "query_params": json.dumps(query_params),
        }
    )
    doc.insert()
    result = {
        "name": doc.name,
        "title": doc.report_title,
        "url": f"/app/ai-report-view?name={frappe.utils.quote(doc.name)}",
        "native_report": None,
        "native_url": None,
    }

    # Also create a NATIVE ERPNext Report record so it appears among the core
    # Reports (/app/report) and opens in the doctype's report view. Report
    # Builder can't group (§4.8), so only listings get a native twin.
    if native and not query_params.get("group_by"):
        try:
            twin = save_as_report(query_params, title, description)
            result["native_report"] = twin["report_name"]
            result["native_url"] = twin["url"]
            doc.db_set("native_report", twin["report_name"], update_modified=False)
        except Exception:
            frappe.logger("ai_report_builder").warning("native report save skipped")

    return result


@frappe.whitelist()
def refine_report(name, instruction):
    """Conversational report refinement: modify a saved report via a natural-
    language instruction, update the saved query (and its native twin), and
    return the refreshed view (Beyond-MVP #2)."""
    from ai_report_builder.ai.query import refine_query
    from ai_report_builder.ai.report import update_native_report

    if not instruction or not instruction.strip():
        frappe.throw(frappe._("Please describe the change."))

    doc = frappe.get_doc("AI Report", name)
    if doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
        frappe.throw(frappe._("Not permitted."), frappe.PermissionError)

    current = json.loads(doc.query_params)
    out = refine_query(current, instruction.strip())
    if out.get("error"):
        return {"error": out["error"], "title": doc.report_title}

    new_params = out["query_params"]
    new_params["doctype"] = current["doctype"]  # never switch doctype
    doc.query_params = json.dumps(new_params)
    doc.report_kind = (
        "Aggregate"
        if (new_params.get("group_by") or new_params.get("aggregate_function"))
        else "Listing"
    )
    doc.save(ignore_permissions=True)

    if doc.native_report:
        update_native_report(doc.native_report, new_params)

    frappe.db.commit()
    return run_ai_report(name)


def _col_meta(field, ref_meta, query_params):
    if field == "_agg":
        fn = query_params.get("aggregate_function")
        label = _AGG_LABEL.get(fn, "Value")
        if fn == "count":
            ftype = "Int"
        else:
            af = query_params.get("aggregate_field")
            dff = ref_meta.get_field(af) if af else None
            ftype = dff.fieldtype if (dff and dff.fieldtype in NUMERIC_TYPES) else "Float"
        return {"field": field, "label": label, "fieldtype": ftype}
    df = ref_meta.get_field(field)
    return {
        "field": field,
        "label": df.label if df else field.replace("_", " ").title(),
        "fieldtype": df.fieldtype if df else "Data",
    }


@frappe.whitelist()
def run_ai_report(name):
    """Load a saved AI Report, re-run it (permission-safe), and return a
    formatted payload: columns (label + fieldtype), rows, totals, chart."""
    doc = frappe.get_doc("AI Report", name)
    if doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
        frappe.throw(frappe._("Not permitted."), frappe.PermissionError)

    query_params = json.loads(doc.query_params)
    result = execute_run_query(**{**query_params, "limit": 500, "limit_cap": 500})
    if result.get("error"):
        return {"error": result["error"], "title": doc.report_title}

    rows = result.get("rows") or []
    ref_meta = frappe.get_meta(doc.reference_doctype)

    keys = list(rows[0].keys()) if rows else []
    columns = [_col_meta(k, ref_meta, query_params) for k in keys]

    # Totals row for numeric columns.
    totals = {}
    for c in columns:
        if c["fieldtype"] in NUMERIC_TYPES:
            totals[c["field"]] = sum((r.get(c["field"]) or 0) for r in rows)

    # Chart for grouped aggregates: group column labels vs the aggregate value.
    chart = None
    if query_params.get("group_by") and "_agg" in keys and len(keys) >= 2:
        label_key = query_params["group_by"].split(".")[0]
        if label_key in keys:
            chart = {
                "labels": [str(r.get(label_key)) for r in rows],
                "values": [r.get("_agg") or 0 for r in rows],
                "title": next((c["label"] for c in columns if c["field"] == "_agg"), "Value"),
            }

    return {
        "title": doc.report_title,
        "description": doc.description,
        "reference_doctype": doc.reference_doctype,
        "columns": columns,
        "rows": rows,
        "totals": totals,
        "chart": chart,
        "count": len(rows),
        "error": None,
    }


def _report_matrix(data):
    """Header + data rows (+ totals row) as a list of lists for export."""
    cols = data["columns"]
    matrix = [[c["label"] for c in cols]]
    for r in data["rows"]:
        matrix.append([r.get(c["field"]) for c in cols])
    if data.get("totals"):
        trow = []
        for i, c in enumerate(cols):
            if i == 0:
                trow.append("Total")
            elif c["field"] in data["totals"]:
                trow.append(data["totals"][c["field"]])
            else:
                trow.append("")
        matrix.append(trow)
    return matrix


@frappe.whitelist()
def export_ai_report(name, file_format="Excel"):
    """Download a saved report as Excel or CSV (server-side, formatted)."""
    data = run_ai_report(name)
    if data.get("error"):
        frappe.throw(frappe._("This report could not be run."))

    matrix = _report_matrix(data)
    safe = "".join(c if c.isalnum() else "_" for c in (data.get("title") or "report"))

    if file_format == "CSV":
        from frappe.utils.csvutils import to_csv

        frappe.response["result"] = to_csv(matrix)
        frappe.response["doctype"] = safe
        frappe.response["type"] = "csv"
    else:
        from frappe.utils.xlsxutils import make_xlsx

        xlsx = make_xlsx(matrix, "AI Report")
        frappe.response["filename"] = f"{safe}.xlsx"
        frappe.response["filecontent"] = xlsx.getvalue()
        frappe.response["type"] = "binary"


@frappe.whitelist()
def list_ai_reports():
    """Current user's saved AI Reports, newest first."""
    return frappe.get_all(
        "AI Report",
        filters={"owner": frappe.session.user},
        fields=["name", "report_title", "reference_doctype", "report_kind", "modified"],
        order_by="modified desc",
        limit=50,
    )
