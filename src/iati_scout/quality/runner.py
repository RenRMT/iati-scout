"""Run all enabled rules over a dataset and produce Findings."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator

from iati_scout.quality.findings import (
    Finding,
    Severity,
    d_portal_activity_url,
    datastore_activity_url,
)
from iati_scout.quality.model import Activity, Dataset
from iati_scout.quality.registry import Context, RuleConfig, RuleSpec, all_rules

logger = logging.getLogger(__name__)


def select_rules(
    config: RuleConfig,
    codes: Iterable[str] | None = None,
    severity: Severity | None = None,
) -> list[RuleSpec]:
    wanted = set(codes) if codes else None
    selected = []
    for spec in all_rules():
        if wanted is not None and spec.code not in wanted:
            continue
        if wanted is None and not config.is_enabled(spec.code):
            continue
        if severity is not None and spec.severity != severity:
            continue
        selected.append(spec)
    if wanted:
        unknown = wanted - {s.code for s in selected}
        if unknown:
            raise ValueError(f"Unknown rule code(s): {', '.join(sorted(unknown))}")
    return selected


def run_rule(spec: RuleSpec, activity: Activity, ctx: Context, systemic: bool) -> Iterator[Finding]:
    for issue in spec.func(activity, ctx):
        yield Finding(
            code=spec.code,
            severity=spec.severity,
            rule_title=spec.title,
            iati_identifier=activity.identifier,
            activity_title=activity.title,
            message=issue.message,
            evidence=issue.evidence,
            item=issue.item,
            related=issue.related,
            urls={
                "d_portal": d_portal_activity_url(activity.identifier),
                "datastore_json": datastore_activity_url(activity.identifier),
            },
            systemic=systemic,
        )


def run_checks(
    dataset: Dataset, config: RuleConfig, rules: list[RuleSpec]
) -> list[Finding]:
    ctx = Context(dataset=dataset, thresholds=config.thresholds)
    findings: list[Finding] = []
    for spec in rules:
        systemic = config.is_systemic(spec.code)
        count = 0
        for activity in dataset:
            for finding in run_rule(spec, activity, ctx, systemic):
                findings.append(finding)
                count += 1
        logger.info("%s %-55s %6d finding(s)", spec.code, spec.title, count)
    return findings
