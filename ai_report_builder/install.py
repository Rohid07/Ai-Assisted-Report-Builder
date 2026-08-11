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


# Starter knowledge base for the docs RAG (Beyond-MVP #6). Users can add more
# via the AI Knowledge Chunk doctype or api.ingest.
DEFAULT_ARTICLES = [
    (
        "Creating a Sales Invoice",
        "To create a Sales Invoice in ERPNext, go to Accounts > Sales Invoice > New. "
        "Select the Customer, add Items with quantity and rate, set the Posting Date "
        "and Due Date, then Save and Submit. On submission the invoice posts accounting "
        "entries to the customer's receivable account.",
    ),
    (
        "Recording a payment against an invoice",
        "To mark a Sales Invoice as paid, open the submitted invoice and click Create > "
        "Payment. This opens a Payment Entry pre-filled with the outstanding amount. "
        "Choose the paid-from/paid-to accounts and Submit. The invoice status changes "
        "from Unpaid or Overdue to Paid once fully settled.",
    ),
    (
        "Scheduling a report by email",
        "Any saved Report can be emailed on a schedule using ERPNext's Auto Email Report. "
        "Go to Auto Email Report > New, pick the Report, set the frequency (daily, weekly, "
        "monthly), the recipients, and the format (CSV, Excel, or PDF). Enable it and the "
        "system sends the report automatically on schedule.",
    ),
    (
        "Exporting a report",
        "Open any Report and use the Menu button. Choose Export to download the data as "
        "CSV or Excel, or Print > PDF to produce a PDF. Report Builder reports inherit "
        "this export functionality with no extra setup.",
    ),
]


def after_install():
    seed_defaults()
    seed_knowledge()


def seed_knowledge(force=False):
    """Seed starter how-to articles for the docs RAG."""
    from ai_report_builder.ai.rag import ingest

    if not force and frappe.db.count("AI Knowledge Chunk"):
        print("Knowledge base already populated, skipping.")
        return
    total = 0
    for title, content in DEFAULT_ARTICLES:
        if not frappe.db.exists("AI Knowledge Chunk", {"title": title}):
            total += ingest(title, content, source="Starter docs")
    print(f"Seeded {total} knowledge chunks.")


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
