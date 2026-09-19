"""Produce Findings from both sources: the official validator report, and scout's own rules."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import Any

from iati_scout.quality.findings import (
    Category,
    Finding,
    Severity,
    Source,
    d_portal_activity_url,
    datastore_activity_url,
)
from iati_scout.quality.model import Activity, Dataset
from iati_scout.quality.registry import Context, RuleConfig, RuleSpec, all_rules

logger = logging.getLogger(__name__)


def select_rules(
    config: RuleConfig,
    codes: Iterable[str] | None = None,
    category: Category | None = None,
) -> list[RuleSpec]:
    wanted = set(codes) if codes else None
    selected = []
    for spec in all_rules():
        if wanted is not None and spec.code not in wanted:
            continue
        if wanted is None and not config.is_enabled(spec.code):
            continue
        if category is not None and spec.category != category:
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
            category=spec.category,
            source=Source.SCOUT,
            rule_title=spec.title,
            iati_identifier=activity.identifier,
            activity_title=activity.title,
            message=issue.message,
            context=[{"text": issue.message}],
            evidence=issue.evidence,
            item=issue.item,
            related=issue.related,
            urls={
                "d_portal": d_portal_activity_url(activity.identifier),
                "datastore_json": datastore_activity_url(activity.identifier),
            },
            systemic=systemic,
        )


def run_checks(dataset: Dataset, config: RuleConfig, rules: list[RuleSpec]) -> list[Finding]:
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


def _category(value: str | None) -> Category:
    """Map a report's category string onto the enum, tolerating an unknown value.

    IATI can add categories without warning; an unrecognised one must not drop
    the finding, so it falls back to `iati` (the validator's own catch-all).
    """
    try:
        return Category(value or "")
    except ValueError:
        logger.debug("Unknown validator category %r; filing under 'iati'", value)
        return Category.IATI


def _severity(value: str | None) -> Severity:
    try:
        return Severity(value or "")
    except ValueError:
        logger.debug("Unknown validator severity %r; treating as 'error'", value)
        return Severity.ERROR


def findings_from_report(report: dict[str, Any]) -> list[Finding]:
    """Flatten one official validator report into Findings.

    The report nests activity -> category -> error; the flat `Finding` keeps
    the activity identity and category on each row so both sources can live in
    one list, and `to_validator_error()` rebuilds the nesting on the way out.
    """
    inner = report.get("report") or {}
    findings: list[Finding] = []
    for activity in inner.get("errors") or []:
        identifier = activity.get("identifier") or ""
        title = activity.get("title") or ""
        for group in activity.get("errors") or []:
            category = _category(group.get("category"))
            for error in group.get("errors") or []:
                findings.append(
                    Finding(
                        code=error.get("id") or "",
                        severity=_severity(error.get("severity")),
                        category=category,
                        source=Source.VALIDATOR,
                        rule_title=error.get("message") or "",
                        iati_identifier=identifier,
                        activity_title=title,
                        message=error.get("message") or "",
                        context=error.get("context") or [],
                        evidence={},
                        item=None,
                        related=[],
                        urls={
                            "d_portal": d_portal_activity_url(identifier),
                            "datastore_json": datastore_activity_url(identifier),
                        },
                        systemic=False,
                    )
                )
    return findings


def findings_from_reports(reports: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    for report in reports:
        document_findings = findings_from_report(report)
        logger.info(
            "%s: %d finding(s) from the official validator",
            report.get("registry_name") or report.get("document_url"),
            len(document_findings),
        )
        findings.extend(document_findings)
    return findings
