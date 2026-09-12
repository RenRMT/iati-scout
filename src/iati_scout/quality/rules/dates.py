"""Section A: activity dates and status."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from iati_scout.quality.findings import Issue, Severity, fmt_date
from iati_scout.quality.model import (
    STATUS_IMPLEMENTATION,
    STATUS_PIPELINE,
    Activity,
)
from iati_scout.quality.registry import Context, rule


@rule("E-A01", Severity.ERROR, "Actual end before actual start")
def actual_end_before_actual_start(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.actual_start and a.actual_end and a.actual_end < a.actual_start:
        yield Issue(
            f"Actual end {fmt_date(a.actual_end)} is before actual start {fmt_date(a.actual_start)}",
            {"actual_start": a.actual_start, "actual_end": a.actual_end},
        )


@rule("E-A02", Severity.ERROR, "Planned end before planned start")
def planned_end_before_planned_start(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.planned_start and a.planned_end and a.planned_end < a.planned_start:
        yield Issue(
            f"Planned end {fmt_date(a.planned_end)} is before planned start "
            f"{fmt_date(a.planned_start)}",
            {"planned_start": a.planned_start, "planned_end": a.planned_end},
        )


@rule("E-A03", Severity.ERROR, "Actual date in the future")
def actual_date_in_future(a: Activity, ctx: Context) -> Iterator[Issue]:
    for label, value in (("actual_start", a.actual_start), ("actual_end", a.actual_end)):
        if value and value > ctx.today:
            yield Issue(
                f"{label.replace('_', ' ').capitalize()} {fmt_date(value)} is after today "
                f"({fmt_date(ctx.today)}); an 'actual' date cannot lie in the future",
                {label: value, "today": ctx.today},
            )


@rule("E-A04", Severity.ERROR, "Pipeline activity with actual start or transactions")
def pipeline_with_activity(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.status != STATUS_PIPELINE:
        return
    if a.actual_start:
        yield Issue(
            f"Status is Pipeline (1) but an actual start date {fmt_date(a.actual_start)} is set",
            {"status": a.status, "actual_start": a.actual_start},
        )
    if a.transactions:
        yield Issue(
            f"Status is Pipeline (1) but {len(a.transactions)} transaction(s) are reported",
            {"status": a.status, "transaction_count": len(a.transactions)},
        )


@rule("E-A05", Severity.ERROR, "Implementation status with actual end date")
def implementation_with_actual_end(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.status == STATUS_IMPLEMENTATION and a.actual_end:
        yield Issue(
            f"Status is Implementation (2) but an actual end date {fmt_date(a.actual_end)} is set",
            {"status": a.status, "actual_end": a.actual_end},
        )


@rule("E-A06", Severity.ERROR, "Closed status without actual end date")
def closed_without_actual_end(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.is_closed and not a.actual_end:
        yield Issue(
            f"Status is {a.status} (finalisation/closed) but no actual end date is reported",
            {"status": a.status, "actual_end": None, "planned_end": a.planned_end},
        )


@rule("W-A07", Severity.WARNING, "Implementation status past planned end")
def implementation_past_planned_end(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.status == STATUS_IMPLEMENTATION and a.planned_end and a.planned_end < ctx.today:
        overdue = (ctx.today - a.planned_end).days
        yield Issue(
            f"Status is Implementation (2) but planned end {fmt_date(a.planned_end)} passed "
            f"{overdue} days ago; status may be stale",
            {"status": a.status, "planned_end": a.planned_end, "days_overdue": overdue},
        )


@rule("W-A08", Severity.WARNING, "Implementation status not updated recently")
def implementation_not_updated(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.status != STATUS_IMPLEMENTATION or not a.last_updated:
        return
    limit = timedelta(days=30 * ctx.t("stale_months"))
    age = ctx.today - a.last_updated.date()
    if age > limit:
        yield Issue(
            f"Status is Implementation (2) but last-updated-datetime "
            f"{fmt_date(a.last_updated.date())} is {age.days} days old",
            {"status": a.status, "last_updated": a.last_updated.date(), "age_days": age.days},
        )


@rule("W-A09", Severity.WARNING, "Transaction dated after last-updated-datetime")
def transaction_after_last_updated(a: Activity, ctx: Context) -> Iterator[Issue]:
    if not a.last_updated:
        return
    cutoff = a.last_updated.date()
    for t in a.transactions:
        if t.date and t.date > cutoff:
            yield Issue(
                f"Transaction on {fmt_date(t.date)} is dated after last-updated-datetime "
                f"{fmt_date(cutoff)}",
                {"transaction_date": t.date, "last_updated": cutoff},
                item=t.locator(),
            )


@rule(
    "E-A10",
    Severity.ERROR,
    "Last-updated-datetime in the future",
    "IATI ruleset 11.1.1: the last-updated-datetime of the activity must not be in "
    "the future.",
)
def last_updated_in_future(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.last_updated and a.last_updated.date() > ctx.today:
        yield Issue(
            f"last-updated-datetime {fmt_date(a.last_updated.date())} is after today "
            f"({fmt_date(ctx.today)})",
            {"last_updated": a.last_updated.date(), "today": ctx.today},
        )


@rule(
    "E-A11",
    Severity.ERROR,
    "No planned or actual start date",
    "IATI ruleset 6.11.1: the activity must have a planned start date or an actual "
    "start date.",
)
def missing_start_date(a: Activity, ctx: Context) -> Iterator[Issue]:
    if not a.planned_start and not a.actual_start:
        yield Issue(
            "Activity has neither a planned start date (type 1) nor an actual start "
            "date (type 2)",
            {"planned_start": None, "actual_start": None},
        )
