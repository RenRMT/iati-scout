"""Section G: results.

The flattened Datastore JSON loses the result -> indicator -> period nesting, so
these rules are activity-level: they look at the presence and format of values,
not at which indicator a period belongs to.
"""

from __future__ import annotations

from collections.abc import Iterator

from iati_scout.quality.findings import Category, Issue
from iati_scout.quality.model import Activity
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


@rule("W-G03", Category.PERFORMANCE, "Closed activity without results")
def closed_without_results(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.is_closed and not a.raw_list("result_type"):
        yield Issue(
            f"Status is {a.status} (finalisation/closed) but no results are reported",
            {"status": a.status, "result_count": 0},
        )


@rule("W-G04", Category.PERFORMANCE, "Closed activity with targets but no actuals")
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
