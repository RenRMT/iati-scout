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
MEASURE_NOMINAL = "3"
MEASURE_ORDINAL = "4"
MEASURE_QUALITATIVE = "5"
# IATI ruleset 8.8.x/8.9.x/8.10.x treat measures 1/2/3/4 collectively as
# "non-qualitative" (must have a numeric value); only 5 (qualitative) is exempt.
NUMERIC_MEASURES = {MEASURE_UNIT, MEASURE_PERCENTAGE, MEASURE_NOMINAL, MEASURE_ORDINAL}


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
                f"use a non-qualitative measure ({'/'.join(sorted(measures))}): {sample}",
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


_VALUE_FIELDS = (
    ("result_indicator_baseline_value", "baseline"),
    ("result_indicator_period_target_value", "target"),
    ("result_indicator_period_actual_value", "actual"),
)


@rule(
    "E-G05",
    Severity.ERROR,
    "Missing baseline value for a non-qualitative indicator",
    "IATI ruleset 8.8.1: the baseline must have a value when the indicator measure "
    "is non-qualitative (1 unit, 2 percentage, 3 nominal, 4 ordinal). Only checked "
    "when every indicator on the activity shares the same non-qualitative measure — "
    "baseline is one value per indicator, so the count is reliable even with the "
    "lost result->indicator nesting; target/actual are one per period and are not "
    "checked here for the same reason E-G01 is scoped the way it is.",
)
def missing_baseline_for_indicator(a: Activity, ctx: Context) -> Iterator[Issue]:
    measures = set(a.raw_list("result_indicator_measure"))
    if not measures or not measures <= NUMERIC_MEASURES:
        return
    indicator_count = len(a.raw_list("result_indicator_measure"))
    present = len([v for v in a.raw_list("result_indicator_baseline_value") if v not in (None, "")])
    if present < indicator_count:
        yield Issue(
            f"{indicator_count - present} of {indicator_count} indicator baseline "
            f"value(s) are missing although all indicators use a non-qualitative "
            f"measure ({'/'.join(sorted(measures))})",
            {"present": present, "expected": indicator_count},
        )


@rule(
    "W-G06",
    Severity.WARNING,
    "Baseline/target/actual value present for a qualitative indicator",
    "IATI ruleset 8.8.3/8.9.3/8.10.3: the value should be omitted for qualitative "
    "(measure 5) indicators. Only checked when every indicator on the activity is "
    "qualitative.",
)
def value_present_for_qualitative_indicator(a: Activity, ctx: Context) -> Iterator[Issue]:
    measures = set(a.raw_list("result_indicator_measure"))
    if measures != {MEASURE_QUALITATIVE}:
        return
    for field, label in _VALUE_FIELDS:
        present = [v for v in a.raw_list(field) if v not in (None, "")]
        if present:
            yield Issue(
                f"{len(present)} indicator {label} value(s) are present although all "
                f"indicators use the qualitative measure (5)",
                {"field": label, "values": present[:20]},
            )
