# AI Report Builder

A natural-language interface that turns business questions into real, saved,
reusable **ERPNext Report** records — not just chat answers.

Ask *"how many customers are in the Commercial group?"* in plain English; the
assistant fetches real ERPNext data and — when the query is savable — persists it
as a native **Report Builder** record that lives inside ERPNext exactly like any
manually built report: reusable, reopenable, schedulable, and exportable
(CSV / Excel / PDF) using ERPNext's own built-in features.

## Differentiator

Other ERPNext AI assistants stop at a chat answer, chart, or CSV export. This one
persists the successful query as a native, reusable `Report` record.

## How it works

Every question flows through a constrained, permission-safe pipeline:

```
question → schema context → LLM (run_query tool) → validation → permission check
        → frappe.get_list() → result table → (optional) Save as Report
```

Security by design:

- **No AI-generated SQL, ever.** The model can only fill a constrained tool schema;
  it never supplies SQL.
- **One permission-safe path.** All execution — including aggregation — goes through
  `frappe.get_list()`, which enforces `has_permission`, User Permissions, and
  company isolation. `frappe.db.get_all` / raw SQL are never used.
- **Allow-list + PII guard.** The model may only reference doctypes on an explicit
  allow-list, and curated sensitive fields are never sent to or returned from the LLM.
- **Read-only on business data.** Report creation is the only write path.

## Configuration

API keys and scope live in the **AI Assistant Settings** single doctype
(System Manager only; keys encrypted at rest via the Password fieldtype):

| Field | Purpose |
|-------|---------|
| Active Provider | Groq / OpenRouter / Ollama |
| Groq / OpenRouter API Key | Encrypted credentials (read server-side only) |
| Allowed Doctypes | Doctypes the assistant may query |
| Sensitive Fields | Fieldnames never sent to / returned from the LLM |
| Enable Audit Logging | Toggle audit logging |

Defaults (Sales Invoice, Purchase Order, Customer, Item) are seeded on install.

## Tech stack

- **Backend:** Python, Frappe Framework (ORM, permissions, Report doctype)
- **LLM:** Groq (primary), OpenRouter (fallback), Ollama (local / on-prem) — all
  OpenAI-compatible via the `openai` SDK
- **Requires:** Frappe / ERPNext v15

## Project status

Built phase by phase per the v3 implementation plan:

- [x] **Phase 0** — Settings doctype + allow-list seeding
- [x] **Phase 1** — Core query loop (single doctype): provider abstraction,
      `run_query` tool + executor, permission-safe aggregation, test suite
- [ ] **Phase 2** — Router, relative-date translation, schema caching
- [ ] **Phase 3** — Chat UI + settings form
- [ ] **Phase 4** — Save as Report (the differentiator)
- [ ] **Phase 5** — Robustness & polish

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app ai_report_builder
```

## Development

Run the test suite:

```bash
bench --site <your-site> run-tests --module ai_report_builder.ai.test_executor
```

This app uses `pre-commit` for code formatting and linting. Please
[install pre-commit](https://pre-commit.com/#installation) and enable it:

```bash
cd apps/ai_report_builder
pre-commit install
```

Configured tools: ruff, eslint, prettier, pyupgrade.

## License

MIT
