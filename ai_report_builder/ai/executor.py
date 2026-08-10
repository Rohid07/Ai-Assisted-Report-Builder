"""run_query executor — the single permission-safe data path (§4.2, §7 Phase 1).

Corrected per v3: aggregation goes through frappe.get_list with a whitelisted
FN(field) as _agg expression. NEVER frappe.db.get_all, NEVER raw SQL — get_list
enforces has_permission, User Permissions, and company isolation in one call.
"""

import frappe

VALID_CONDITIONS = {
    "=", "!=", ">", "<", ">=", "<=",
    "like", "not like", "in", "not in", "between", "is", "is not",
}

# Aggregate functions are whitelisted here; the MODEL never supplies SQL.
AGG_FUNCS = {"sum": "SUM", "count": "COUNT", "avg": "AVG"}

# Framework fields always allowed as plain columns even if not in meta.fields.
STANDARD_FIELDS = {
    "name", "owner", "creation", "modified", "modified_by",
    "docstatus", "idx", "parent", "parentfield", "parenttype",
}


def get_settings():
    return frappe.get_single("AI Assistant Settings")


def get_allowed_doctypes():
    return {d.document_type for d in get_settings().allowed_doctypes}


def get_sensitive_fields(doctype):
    return {
        d.field_name
        for d in get_settings().sensitive_fields
        if d.document_type == doctype
    }


def check_allowlist(doctype):
    """§4.4 — the model may only touch doctypes on the explicit allow-list."""
    if doctype not in get_allowed_doctypes():
        frappe.throw(f"Doctype '{doctype}' is not enabled for the assistant.")


def validate_filters(filters):
    """§7 — hardened to reject non-list rows and unsupported operators."""
    for f in filters or []:
        if not isinstance(f, (list, tuple)) or len(f) < 3:
            frappe.throw(f"Malformed filter: {f}")
        if f[-2] not in VALID_CONDITIONS:
            frappe.throw(f"Unsupported filter condition: {f[-2]}")


def _valid_fieldnames(doctype):
    meta = frappe.get_meta(doctype)
    return {df.fieldname for df in meta.get("fields")} | STANDARD_FIELDS


def _validate_plain_field(field, valid, sensitive, doctype):
    """A single plain fieldname (no SQL expressions allowed here)."""
    fieldname = field.split(".")[0].strip()
    if fieldname in sensitive:
        frappe.throw(f"Field '{fieldname}' on {doctype} is not accessible.")
    if fieldname not in valid:
        frappe.throw(f"Unknown field '{fieldname}' on {doctype}.")
    return fieldname


def _agg_field(aggregate_function, aggregate_field):
    """Build a whitelisted aggregate expression. Fieldname is validated
    against the doctype meta by the caller; the function is whitelisted here."""
    fn = AGG_FUNCS[aggregate_function]  # KeyError-safe: enum-constrained upstream
    inner = "name" if aggregate_function == "count" else aggregate_field
    return f"{fn}(`{inner}`) as _agg"


def execute_run_query(
    doctype,
    filters=None,
    fields=None,
    group_by=None,
    aggregate_function=None,
    aggregate_field=None,
    order_by=None,
    limit=50,
):
    # §4.4 allow-list, then §4.2/§4.6 permission gate. get_list ALSO enforces
    # permission, but we fail early & clean with a structured error.
    check_allowlist(doctype)
    if not frappe.has_permission(doctype, "read"):
        return {"error": "permission_denied", "doctype": doctype}

    validate_filters(filters)
    limit = min(limit or 50, 200)

    valid = _valid_fieldnames(doctype)
    sensitive = get_sensitive_fields(doctype)

    # Validate group_by / order_by / aggregate_field against meta (anti-injection).
    if group_by:
        _validate_plain_field(group_by, valid, sensitive, doctype)
    if order_by:
        _validate_plain_field(order_by, valid, sensitive, doctype)

    if aggregate_function:
        if aggregate_function not in AGG_FUNCS:
            frappe.throw(f"Unsupported aggregate function: {aggregate_function}")
        if aggregate_function != "count":
            if not aggregate_field:
                frappe.throw("aggregate_field is required for sum/avg.")
            _validate_plain_field(aggregate_field, valid, sensitive, doctype)
        # group_by columns first, then the aggregate — matches SQL semantics.
        select_fields = ([group_by] if group_by else []) + [
            _agg_field(aggregate_function, aggregate_field)
        ]
    else:
        # Plain listing: validate & drop sensitive/unknown fields.
        requested = list(fields or ["name"])
        select_fields = [
            _validate_plain_field(f, valid, sensitive, doctype) for f in requested
        ] or ["name"]

    # ONE call. get_list enforces permissions, User Permissions, company isolation.
    rows = frappe.get_list(
        doctype,
        filters=filters or [],
        fields=select_fields,
        group_by=group_by,
        order_by=order_by,
        limit_page_length=limit,
    )
    return {"rows": rows, "count": len(rows)}
