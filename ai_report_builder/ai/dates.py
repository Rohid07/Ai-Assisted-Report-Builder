"""Relative-date translation — step [0] of the flow (§3, §7 Phase 2).

Turns phrases like "last month", "this quarter", "Q1", "last 30 days" into
concrete (from_date, to_date) ranges. Two uses:
  - resolve_date_phrase(): deterministic helper (unit-tested).
  - date_context(): a compact block injected into the prompt so the LLM emits
    concrete `between` filters instead of guessing dates.
"""

from frappe.utils import (
    add_days,
    add_months,
    add_years,
    get_first_day,
    get_last_day,
    get_year_ending,
    get_year_start,
    getdate,
    nowdate,
)

# Common phrases surfaced in the prompt so the model resolves them consistently.
COMMON_PHRASES = [
    "today",
    "yesterday",
    "this week",
    "last week",
    "this month",
    "last month",
    "this quarter",
    "last quarter",
    "this year",
    "last year",
    "year to date",
]


def _quarter_range(year, q):
    start_month = (q - 1) * 3 + 1
    start = getdate(f"{year}-{start_month:02d}-01")
    end = get_last_day(add_months(start, 2))
    return start, end


def resolve_date_phrase(phrase, today=None):
    """Return (from_date, to_date) as date objects, or None if unrecognized."""
    if not phrase:
        return None
    today = getdate(today or nowdate())
    p = " ".join(phrase.strip().lower().split())

    if p == "today":
        return today, today
    if p == "yesterday":
        y = add_days(today, -1)
        return y, y

    if p == "this week":
        start = add_days(today, -today.weekday())  # Monday
        return start, add_days(start, 6)
    if p == "last week":
        start = add_days(today, -today.weekday() - 7)
        return start, add_days(start, 6)

    if p == "this month":
        return get_first_day(today), get_last_day(today)
    if p == "last month":
        prev = add_months(today, -1)
        return get_first_day(prev), get_last_day(prev)

    if p in ("this year", "year to date", "ytd"):
        return get_year_start(today), (today if p in ("year to date", "ytd") else get_year_ending(today))
    if p == "last year":
        ly = add_years(today, -1)
        return get_year_start(ly), get_year_ending(ly)

    if p == "this quarter":
        return _quarter_range(today.year, (today.month - 1) // 3 + 1)
    if p == "last quarter":
        cur_q = (today.month - 1) // 3 + 1
        if cur_q == 1:
            return _quarter_range(today.year - 1, 4)
        return _quarter_range(today.year, cur_q - 1)

    # Q1..Q4 of the current year
    if p in ("q1", "q2", "q3", "q4"):
        return _quarter_range(today.year, int(p[1]))

    # "last N days" / "last N months"
    parts = p.split()
    if len(parts) == 3 and parts[0] == "last" and parts[1].isdigit():
        n = int(parts[1])
        if parts[2] in ("day", "days"):
            return add_days(today, -n), today
        if parts[2] in ("month", "months"):
            return add_months(today, -n), today

    return None


def date_context(today=None):
    """A compact prompt block: today's date + resolved common ranges, so the
    model can emit concrete date filters."""
    today = getdate(today or nowdate())
    lines = [f"Today's date is {today.isoformat()}. Resolved date ranges:"]
    for phrase in COMMON_PHRASES:
        r = resolve_date_phrase(phrase, today)
        if r:
            lines.append(f"- {phrase}: {r[0].isoformat()} to {r[1].isoformat()}")
    lines.append(
        "When the question refers to a time period, use these ranges in a "
        "`between` filter, e.g. [\"posting_date\", \"between\", [\"<from>\", \"<to>\"]]."
    )
    return "\n".join(lines)
