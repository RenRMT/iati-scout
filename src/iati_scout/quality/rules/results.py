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
