import frappe

# Curated defaults. Kept deliberately small (§4.4): controls schema size,
# product scope, and keeps the model out of HR/salary/system doctypes.
DEFAULT_ALLOWED_DOCTYPES = [
    "Sales Invoice",
    "Purchase Order",
    "Customer",
    "Item",
]

# Fieldnames never sent to / returned from the LLM (§4.3).
DEFAULT_SENSITIVE_FIELDS = [
    ("Customer", "tax_id"),
]


def after_install():
    seed_defaults()


def seed_defaults(force=False):
    """Seed the assistant's allow-list and sensitive-field defaults.
    Idempotent: only fills empty tables unless force=True."""
    settings = frappe.get_single("AI Assistant Settings")

    if force or not settings.allowed_doctypes:
        settings.allowed_doctypes = []
        for dt in DEFAULT_ALLOWED_DOCTYPES:
            if frappe.db.exists("DocType", dt):
                settings.append("allowed_doctypes", {"document_type": dt})

    if force or not settings.sensitive_fields:
        settings.sensitive_fields = []
        for dt, field in DEFAULT_SENSITIVE_FIELDS:
            if frappe.db.exists("DocType", dt):
                settings.append(
                    "sensitive_fields", {"document_type": dt, "field_name": field}
                )

    if settings.audit_enabled is None:
        settings.audit_enabled = 1

    settings.save(ignore_permissions=True)
    frappe.db.commit()
    print(
        f"Seeded: {len(settings.allowed_doctypes)} allowed doctypes, "
        f"{len(settings.sensitive_fields)} sensitive fields."
    )
