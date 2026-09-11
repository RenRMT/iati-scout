"""Section G: results.

The flattened Datastore JSON loses the result -> indicator -> period nesting, so
these rules are activity-level: they look at the presence and format of values,
not at which indicator a period belongs to.
"""

from __future__ import annotations

from collections.abc import Iterator

from iati_scout.quality.findings import Issue, Severity, fmt_date
from iati_scout.quality.model import Activity, parse_date
from iati_scout.quality.registry import Context, rule

MEASURE_UNIT = "1"
MEASURE_PERCENTAGE = "2"
NUMERIC_MEASURES = {MEASURE_UNIT, MEASURE_PERCENTAGE}


def _non_numeric(values: list) -> list[str]:
    bad = []
    for v in values:
        try:
            float(v)
        except (TypeError, ValueError):
            bad.append(str(v))
    return bad


@rule("E-G01", Severity.ERROR, "Non-numeric indicator values")
def non_numeric_indicator_values(a: Activity, ctx: Context) -> Iterator[Issue]:
    measures = set(a.raw_list("result_indicator_measure"))
    # Only meaningful when every indicator is a unit/percentage measure; with the
    # nesting lost we cannot attribute values to a specific indicator.
    if not measures or not measures <= NUMERIC_MEASURES:
        return
    for field, label in (
        ("result_indicator_baseline_value", "baseline"),
        ("result_indicator_period_target_value", "target"),
        ("result_indicator_period_actual_value", "actual"),
    ):
        bad = _non_numeric(a.raw_list(field))
        if bad:
            sample = ", ".join(f"'{b}'" for b in bad[:3])
            yield Issue(
                f"{len(bad)} indicator {label} value(s) are not numeric although all indicators "
                f"use measure {'/'.join(sorted(measures))} (unit/percentage): {sample}",
                {"field": label, "non_numeric_values": bad[:20], "measures": sorted(measures)},
            )


@rule("E-G02", Severity.ERROR, "Result period end before start")
def result_period_end_before_start(a: Activity, ctx: Context) -> Iterator[Issue]:
    starts = a.raw_list("result_indicator_period_period_start_iso_date")
    ends = a.raw_list("result_indicator_period_period_end_iso_date")
    for i, (s, e) in enumerate(zip(starts, ends)):
        start, end = parse_date(s), parse_date(e)
        if start and end and end < start:
            yield Issue(
                f"Result period #{i + 1} ends {fmt_date(end)} before it starts {fmt_date(start)}",
                {"period_index": i, "period_start": start, "period_end": end},
            )


@rule("W-G03", Severity.WARNING, "Closed activity without results")
def closed_without_results(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.is_closed and not a.raw_list("result_type"):
        yield Issue(
            f"Status is {a.status} (finalisation/closed) but no results are reported",
            {"status": a.status, "result_count": 0},
        )


@rule("W-G04", Severity.WARNING, "Closed activity with targets but no actuals")
def closed_targets_without_actuals(a: Activity, ctx: Context) -> Iterator[Issue]:
    targets = a.raw_list("result_indicator_period_target_value")
    actuals = a.raw_list("result_indicator_period_actual_value")
    if a.is_closed and targets and not actuals:
        yield Issue(
            f"Status is {a.status} (finalisation/closed) with {len(targets)} indicator target(s) "
            f"but no actual values",
            {"status": a.status, "target_count": len(targets), "actual_count": 0},
        )
