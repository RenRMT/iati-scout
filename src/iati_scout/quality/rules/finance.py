"""Section B: financial consistency across budgets and transactions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from itertools import pairwise

from iati_scout.quality.findings import Category, Issue, fmt_date, fmt_money
from iati_scout.quality.model import (
    ORG_TYPE_OTHER,
    OUTGOING_TXN_TYPES,
    TXN_COMMITMENT,
    TXN_DISBURSEMENT,
    TXN_EXPENDITURE,
    Activity,
)
from iati_scout.quality.registry import Context, rule

TXN_TYPE_NAMES = {
    "1": "Incoming Funds",
    "2": "Outgoing Commitment",
    "3": "Disbursement",
    "4": "Expenditure",
    "11": "Incoming Commitment",
}


def _txn_name(code: str) -> str:
    return f"{TXN_TYPE_NAMES.get(code, 'type ' + code)} ({code})"


# --- budgets ---------------------------------------------------------------


@rule("E-B02", Category.FINANCIAL, "Budget value-date outside budget period")
def budget_value_date_outside_period(a: Activity, ctx: Context) -> Iterator[Issue]:
    for b in a.budgets:
        if not (b.period_start and b.period_end and b.value_date):
            continue
        lo, hi = sorted((b.period_start, b.period_end))
        if not (lo <= b.value_date <= hi):
            yield Issue(
                f"Budget value-date {fmt_date(b.value_date)} lies outside the budget period "
                f"{fmt_date(b.period_start)} – {fmt_date(b.period_end)}",
                {
                    "value_date": b.value_date,
                    "period_start": b.period_start,
                    "period_end": b.period_end,
                },
                item=b.locator(),
            )


@rule("E-B03", Category.FINANCIAL, "Negative budget value")
def negative_budget(a: Activity, ctx: Context) -> Iterator[Issue]:
    for b in a.budgets:
        if b.value < 0:
            yield Issue(
                f"Budget for {fmt_date(b.period_start)} – {fmt_date(b.period_end)} has a negative "
                f"value {fmt_money(b.value, b.currency)}; budgets are forward-looking plans and "
                f"corrections should be published as a revised budget (type 2)",
                {"value": b.value, "budget_type": b.type, "budget_status": b.status},
                item=b.locator(),
            )


@rule("W-B05", Category.FINANCIAL, "Overlapping budget periods")
def budget_periods_overlap(a: Activity, ctx: Context) -> Iterator[Issue]:
    periods = sorted(
        (b for b in a.budgets if b.period_start and b.period_end and b.period_start <= b.period_end),
        key=lambda b: (b.period_start, b.period_end),
    )
    for prev, cur in pairwise(periods):
        if cur.period_start < prev.period_end:
            yield Issue(
                f"Budget period {fmt_date(cur.period_start)} – {fmt_date(cur.period_end)} "
                f"overlaps the previous period {fmt_date(prev.period_start)} – "
                f"{fmt_date(prev.period_end)}",
                {
                    "previous": [prev.period_start, prev.period_end, prev.value],
                    "current": [cur.period_start, cur.period_end, cur.value],
                },
                item=cur.locator(),
            )


@rule("W-B06", Category.FINANCIAL, "Budget period shorter than one month")
def budget_period_too_short(a: Activity, ctx: Context) -> Iterator[Issue]:
    min_days = ctx.t("budget_min_days")
    for b in a.budgets:
        if b.period_start and b.period_end and b.period_start <= b.period_end:
            days = (b.period_end - b.period_start).days
            if days < min_days:
                yield Issue(
                    f"Budget period {fmt_date(b.period_start)} – {fmt_date(b.period_end)} is only "
                    f"{days} days long",
                    {"period_start": b.period_start, "period_end": b.period_end, "days": days},
                    item=b.locator(),
                )


@rule("W-B07", Category.FINANCIAL, "Zero-value budget or transaction")
def zero_values(a: Activity, ctx: Context) -> Iterator[Issue]:
    for b in a.budgets:
        if b.value == 0:
            yield Issue(
                f"Budget for {fmt_date(b.period_start)} – {fmt_date(b.period_end)} has value 0",
                {"value": 0.0},
                item=b.locator(),
            )
    for t in a.transactions:
        if t.value == 0:
            yield Issue(
                f"{_txn_name(t.type)} on {fmt_date(t.date)} has value 0",
                {"value": 0.0, "transaction_type": t.type},
                item=t.locator(),
            )


# --- transactions ----------------------------------------------------------


@rule("W-B08", Category.FINANCIAL, "Negative disbursement or expenditure")
def negative_disbursement(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if t.type in (TXN_DISBURSEMENT, TXN_EXPENDITURE) and t.value < 0:
            yield Issue(
                f"{_txn_name(t.type)} on {fmt_date(t.date)} is negative: "
                f"{fmt_money(t.value, t.currency)}"
                + (f" to {t.receiver_name}" if t.receiver_name else "")
                + "; verify it is a genuine reversal",
                {"value": t.value, "transaction_type": t.type, "receiver": t.receiver_name},
                item=t.locator(),
            )


@rule("E-B09", Category.FINANCIAL, "Disbursed more than committed")
def disbursed_exceeds_committed(a: Activity, ctx: Context) -> Iterator[Issue]:
    committed = a.sum_transactions(TXN_COMMITMENT)
    spent = a.sum_transactions(TXN_DISBURSEMENT, TXN_EXPENDITURE)
    if committed > 0 and spent > committed * (1 + ctx.t("commitment_tolerance")):
        yield Issue(
            f"Disbursements + expenditure {fmt_money(spent, a.currency)} exceed total commitments "
            f"{fmt_money(committed, a.currency)}",
            {"committed": committed, "disbursed_and_expended": spent, "currency": a.currency},
        )


@rule("W-B10", Category.FINANCIAL, "Disbursements without any commitment")
def disbursed_without_commitment(a: Activity, ctx: Context) -> Iterator[Issue]:
    committed = a.sum_transactions(TXN_COMMITMENT)
    spent = a.sum_transactions(TXN_DISBURSEMENT, TXN_EXPENDITURE)
    if spent > 0 and committed == 0:
        yield Issue(
            f"{fmt_money(spent, a.currency)} disbursed/expended but no outgoing commitment "
            f"(type 2) reported",
            {"committed": 0.0, "disbursed_and_expended": spent, "currency": a.currency},
        )


@rule("W-B11", Category.FINANCIAL, "Closed activity with zero disbursements")
def closed_without_disbursement(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.is_closed and a.sum_transactions(TXN_DISBURSEMENT, TXN_EXPENDITURE) == 0:
        committed = a.sum_transactions(TXN_COMMITMENT)
        yield Issue(
            f"Status is {a.status} (finalisation/closed) but no disbursement or expenditure "
            f"was reported (commitments {fmt_money(committed, a.currency)})",
            {"status": a.status, "committed": committed, "disbursed_and_expended": 0.0},
        )


@rule("W-B12", Category.FINANCIAL, "Closed activity with commitment not fully disbursed")
def closed_not_fully_disbursed(a: Activity, ctx: Context) -> Iterator[Issue]:
    if not a.is_closed:
        return
    committed = a.sum_transactions(TXN_COMMITMENT)
    spent = a.sum_transactions(TXN_DISBURSEMENT, TXN_EXPENDITURE)
    if committed > 0 and 0 < spent < committed * (1 - ctx.t("disbursed_tolerance")):
        yield Issue(
            f"Status is {a.status} (finalisation/closed) but only {fmt_money(spent, a.currency)} of "
            f"{fmt_money(committed, a.currency)} committed was disbursed/expended "
            f"({spent / committed:.0%})",
            {
                "status": a.status,
                "committed": committed,
                "disbursed_and_expended": spent,
                "ratio": round(spent / committed, 4),
            },
        )


@rule("W-B13", Category.FINANCIAL, "Transaction outside activity dates")
def transaction_outside_activity_dates(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if not t.date:
            continue
        if a.actual_start and t.date < a.actual_start:
            yield Issue(
                f"{_txn_name(t.type)} on {fmt_date(t.date)} is before actual start "
                f"{fmt_date(a.actual_start)}",
                {"transaction_date": t.date, "actual_start": a.actual_start},
                item=t.locator(),
            )
        if a.actual_end and t.date > a.actual_end:
            yield Issue(
                f"{_txn_name(t.type)} on {fmt_date(t.date)} is after actual end "
                f"{fmt_date(a.actual_end)}",
                {"transaction_date": t.date, "actual_end": a.actual_end},
                item=t.locator(),
            )


@rule("W-B14", Category.FINANCIAL, "Outgoing transaction to the reporting organisation itself")
def receiver_is_reporting_org(a: Activity, ctx: Context) -> Iterator[Issue]:
    own_names = {n.strip().lower() for n in a.reporting_org_names if n}
    own_ref = (a.reporting_org_ref or "").strip().lower()
    for t in a.transactions:
        if t.type not in OUTGOING_TXN_TYPES:
            continue
        name = (t.receiver_name or "").strip().lower()
        ref = (t.receiver_ref or "").strip().lower()
        if (name and name in own_names) or (ref and ref == own_ref):
            yield Issue(
                f"{_txn_name(t.type)} of {fmt_money(t.value, t.currency)} on {fmt_date(t.date)} "
                f"names the reporting organisation ({t.receiver_name or t.receiver_ref}) as receiver",
                {"receiver_name": t.receiver_name, "receiver_ref": t.receiver_ref},
                item=t.locator(),
            )


@rule("W-B15", Category.FINANCIAL, "Duplicate transaction")
def duplicate_transaction(a: Activity, ctx: Context) -> Iterator[Issue]:
    seen: Counter[tuple] = Counter()
    for t in a.transactions:
        key = (t.type, t.date, t.value, t.receiver_name)
        seen[key] += 1
        if seen[key] == 2:
            yield Issue(
                f"{_txn_name(t.type)} of {fmt_money(t.value, t.currency)} on {fmt_date(t.date)}"
                + (f" to {t.receiver_name}" if t.receiver_name else "")
                + " appears more than once",
                {"transaction_type": t.type, "date": t.date, "value": t.value},
                item=t.locator(),
            )


@rule("W-B16", Category.FINANCIAL, "Outgoing transaction without receiver organisation")
def outgoing_without_receiver(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if t.type in OUTGOING_TXN_TYPES and not t.receiver_name and not t.receiver_ref:
            yield Issue(
                f"{_txn_name(t.type)} of {fmt_money(t.value, t.currency)} on {fmt_date(t.date)} "
                f"has no receiver organisation",
                {"transaction_type": t.type, "receiver_name": None, "receiver_ref": None},
                item=t.locator(),
            )


@rule("W-B17", Category.FINANCIAL, "Receiver organisation type 'Other'")
def receiver_type_other(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if t.receiver_type == ORG_TYPE_OTHER:
            yield Issue(
                f"Receiver {t.receiver_name or t.receiver_ref or '(unnamed)'} on {fmt_date(t.date)} "
                f"is typed 90 (Other); a specific organisation type is expected",
                {"receiver_name": t.receiver_name, "receiver_type": t.receiver_type},
                item=t.locator(),
            )


@rule("W-B18", Category.FINANCIAL, "Value-date far from transaction-date")
def value_date_far_from_transaction_date(a: Activity, ctx: Context) -> Iterator[Issue]:
    max_days = ctx.t("value_date_max_days")
    for t in a.transactions:
        if t.date and t.value_date:
            gap = abs((t.value_date - t.date).days)
            if gap > max_days:
                yield Issue(
                    f"{_txn_name(t.type)} dated {fmt_date(t.date)} has value-date "
                    f"{fmt_date(t.value_date)}, {gap} days apart",
                    {"transaction_date": t.date, "value_date": t.value_date, "gap_days": gap},
                    item=t.locator(),
                )


@rule("W-B19", Category.FINANCIAL, "Outlier transaction value")
def outlier_transaction_value(a: Activity, ctx: Context) -> Iterator[Issue]:
    p99 = ctx.dataset.transaction_value_p99
    min_value = ctx.t("min_transaction_value")
    for t in a.transactions:
        magnitude = abs(t.value)
        if magnitude == 0:
            continue
        if magnitude < min_value:
            yield Issue(
                f"{_txn_name(t.type)} on {fmt_date(t.date)} has a tiny value "
                f"{fmt_money(t.value, t.currency)}",
                {"value": t.value, "threshold": min_value},
                item=t.locator(),
            )
        elif p99 is not None and magnitude > p99:
            yield Issue(
                f"{_txn_name(t.type)} on {fmt_date(t.date)} of {fmt_money(t.value, t.currency)} "
                f"exceeds the organisation's 99th percentile ({fmt_money(p99, t.currency)})",
                {"value": t.value, "p99": round(p99, 2)},
                item=t.locator(),
            )


@rule("W-B20", Category.FINANCIAL, "Total budget far from total commitment")
def budget_vs_commitment(a: Activity, ctx: Context) -> Iterator[Issue]:
    committed = a.sum_transactions(TXN_COMMITMENT)
    budgeted = sum(b.value for b in a.budgets)
    if committed > 0 and budgeted > 0:
        ratio = abs(budgeted - committed) / committed
        if ratio > ctx.t("budget_vs_commitment_ratio"):
            yield Issue(
                f"Total budget {fmt_money(budgeted, a.currency)} differs {ratio:.0%} from total "
                f"commitment {fmt_money(committed, a.currency)}",
                {"budget_total": budgeted, "committed": committed, "ratio": round(ratio, 4)},
            )


@rule("W-B21", Category.FINANCIAL, "Transaction dated on 1 January or 31 December")
def transaction_on_year_boundary(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if t.date and (t.date.month, t.date.day) in ((1, 1), (12, 31)):
            yield Issue(
                f"{_txn_name(t.type)} of {fmt_money(t.value, t.currency)} is dated "
                f"{fmt_date(t.date)}; year-boundary dates often indicate a placeholder date",
                {"transaction_date": t.date},
                item=t.locator(),
            )


def transaction_date_in_future(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if t.date and t.date > ctx.today:
            yield Issue(
                f"{_txn_name(t.type)} is dated {fmt_date(t.date)}, after today "
                f"({fmt_date(ctx.today)})",
                {"transaction_date": t.date, "today": ctx.today},
                item=t.locator(),
            )


def transaction_value_date_in_future(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if t.value_date and t.value_date > ctx.today:
            yield Issue(
                f"{_txn_name(t.type)} has value-date {fmt_date(t.value_date)}, after "
                f"today ({fmt_date(ctx.today)})",
                {"value_date": t.value_date, "today": ctx.today},
                item=t.locator(),
            )


def currency_missing(a: Activity, ctx: Context) -> Iterator[Issue]:
    for t in a.transactions:
        if not t.currency:
            yield Issue(
                f"{_txn_name(t.type)} of {t.value:g} on {fmt_date(t.date)} has no "
                f"currency, and the activity has no default-currency either",
                {"value": t.value},
                item=t.locator(),
            )
    for b in a.budgets:
        if not b.currency:
            yield Issue(
                f"Budget for {fmt_date(b.period_start)} – {fmt_date(b.period_end)} of "
                f"{b.value:g} has no currency, and the activity has no default-currency "
                f"either",
                {"value": b.value},
                item=b.locator(),
            )
