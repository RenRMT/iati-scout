"""Write findings to disk in the official IATI Validator report shape.

Three files, all carrying the same findings:

- `report.json`    — canonical, structured exactly like the validator's own
                     report so existing IATI tooling can read it
- `findings.csv`   — flattened, one row per finding, for spreadsheets
- `summary.md`     — counts and samples for a human

`report.json` follows the IATI Validator API Contract: activity -> category ->
error, with a `summary` of counts per severity. Scout's additions are
namespaced rather than mixed in — a top-level `scout` block for run metadata,
and per-finding extras under the contract's free-form `details` object — so a
consumer that only knows the official schema still parses it correctly.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from iati_scout import __version__
from iati_scout.quality.findings import SEVERITY_ORDER, Finding, Severity, Source
from iati_scout.quality.registry import RuleSpec

CSV_COLUMNS = [
    "id",
    "severity",
    "category",
    "source",
    "rule_title",
    "iati_identifier",
    "activity_title",
    "message",
    "context",
    "evidence",
    "item",
    "related",
    "d_portal_url",
    "systemic",
]

SAMPLES_PER_RULE = 3


def build_report(
    findings: list[Finding],
    rules: list[RuleSpec],
    org_id: str,
    activity_count: int,
    validator_reports: list[dict[str, Any]],
    known_identifiers: set[str] | None = None,
) -> dict[str, Any]:
    """Merge validator and scout findings into one official-shaped report.

    `known_identifiers` is the set of activities present in the fetched
    Datastore data. The validator reads the publisher's XML directly, so it can
    report activities the Datastore has not ingested yet; those identifiers are
    counted separately rather than silently pushing `activities_affected`
    above `activity_count`.
    """
    by_activity: dict[str, list[Finding]] = defaultdict(list)
    titles: dict[str, str] = {}
    for finding in findings:
        by_activity[finding.iati_identifier].append(finding)
        if finding.activity_title:
            titles.setdefault(finding.iati_identifier, finding.activity_title)

    activities = []
    for identifier in sorted(by_activity):
        groups: dict[str, list[Finding]] = defaultdict(list)
        for finding in by_activity[identifier]:
            groups[finding.category.value].append(finding)
        activities.append(
            {
                "identifier": identifier,
                "title": titles.get(identifier, ""),
                "errors": [
                    {
                        "category": category,
                        "errors": [f.to_validator_error() for f in groups[category]],
                    }
                    for category in sorted(groups)
                ],
            }
        )

    severity_totals = Counter(f.severity for f in findings)
    summary = {s.value: severity_totals.get(s, 0) for s in SEVERITY_ORDER}
    # `valid` means "no critical or error from the official ruleset". A scout
    # advisory is never a standard violation, so it cannot make a file invalid.
    valid = all(r.get("valid", True) for r in validator_reports) if validator_reports else None

    first = (validator_reports[0].get("report") or {}) if validator_reports else {}
    return {
        "valid": valid,
        "report": {
            "valid": valid,
            "fileType": first.get("fileType"),
            "iatiVersion": first.get("iatiVersion"),
            "rulesetCommitSha": first.get("rulesetCommitSha"),
            "codelistCommitSha": first.get("codelistCommitSha"),
            "orgIdPrefixFileName": first.get("orgIdPrefixFileName"),
            "apiVersion": first.get("apiVersion"),
            "summary": summary,
            "errors": activities,
        },
        "scout": {
            "org_id": org_id,
            "tool_version": __version__,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "activity_count": activity_count,
            "activities_affected": len(by_activity),
            # Published (and so validated) but absent from the Datastore: either
            # the Datastore has not re-ingested the file yet, or those
            # activities failed ingestion. Scout rules cannot run on them.
            "activities_not_in_datastore": sorted(set(by_activity) - known_identifiers)
            if known_identifiers is not None
            else [],
            "per_source": dict(Counter(f.source.value for f in findings)),
            "rules_run": [spec.code for spec in rules],
            "documents": [
                {
                    "registry_name": r.get("registry_name"),
                    "document_url": r.get("document_url"),
                    "registry_hash": r.get("registry_hash"),
                    "valid": r.get("valid"),
                    "summary": (r.get("report") or {}).get("summary") or {},
                }
                for r in validator_reports
            ],
        },
    }


def write_report_json(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_findings_csv(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for finding in findings:
            data = finding.to_dict()
            writer.writerow(
                {
                    "id": data["code"],
                    "severity": data["severity"],
                    "category": data["category"],
                    "source": data["source"],
                    "rule_title": data["rule_title"],
                    "iati_identifier": data["iati_identifier"],
                    "activity_title": data["activity_title"],
                    "message": data["message"],
                    "context": " | ".join(c.get("text", "") for c in data["context"]),
                    "evidence": json.dumps(data["evidence"], ensure_ascii=False),
                    "item": json.dumps(data["item"], ensure_ascii=False) if data["item"] else "",
                    "related": ";".join(r["identifier"] for r in data["related"]),
                    "d_portal_url": data["urls"].get("d_portal", ""),
                    "systemic": data["systemic"],
                }
            )


def build_summary(
    findings: list[Finding],
    rules: list[RuleSpec],
    org_id: str,
    activity_count: int,
    validator_reports: list[dict[str, Any]],
    known_identifiers: set[str] | None = None,
) -> str:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.code].append(finding)
    severity_totals = Counter(f.severity for f in findings)
    affected = len({f.iati_identifier for f in findings})
    rule_titles = {spec.code: spec.title for spec in rules}

    lines = [
        f"# Data-quality summary for {org_id}",
        "",
        (
            f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} over "
            f"{activity_count} activities."
        ),
        "",
    ]

    if validator_reports:
        lines += ["## Documents validated by IATI", "", "| Document | Valid | Ruleset commit |", "|---|:-:|---|"]
        for r in validator_reports:
            inner = r.get("report") or {}
            lines.append(
                f"| [{r.get('registry_name')}]({r.get('document_url')}) | "
                f"{'yes' if r.get('valid') else 'NO'} | "
                f"`{(inner.get('rulesetCommitSha') or '')[:10]}` |"
            )
        lines.append("")

    lines += ["## Totals", ""]
    for severity in SEVERITY_ORDER:
        lines.append(f"- {severity.value.title()}: **{severity_totals.get(severity, 0)}**")
    if activity_count:
        in_datastore = (
            len({f.iati_identifier for f in findings} & known_identifiers)
            if known_identifiers is not None
            else affected
        )
        lines.append(
            f"- Activities with at least one finding: **{in_datastore}** of {activity_count} "
            f"({in_datastore / activity_count:.0%})"
        )
    if known_identifiers is not None:
        unknown = {f.iati_identifier for f in findings} - known_identifiers
        if unknown:
            lines.append(
                f"- Published and validated but **not in the Datastore**: {len(unknown)} "
                "activities (the Datastore has not ingested them; scout rules could not run "
                "on them)"
            )
    lines.append("")

    for source, heading in (
        (Source.VALIDATOR, "Official IATI validator findings"),
        (Source.SCOUT, "Additional iati-scout findings"),
    ):
        codes = sorted({f.code for f in findings if f.source == source})
        if not codes:
            continue
        lines += [
            f"## {heading}",
            "",
            "| Rule | Severity | Category | Findings | Activities | Systemic |",
            "|---|---|---|---:|---:|:-:|",
        ]
        for code in sorted(codes, key=lambda c: -len(by_rule[c])):
            fs = by_rule[code]
            label = rule_titles.get(code, fs[0].message[:60])
            systemic = "yes" if fs[0].systemic else ""
            lines.append(
                f"| {code} — {label} | {fs[0].severity.value} | {fs[0].category.value} | "
                f"{len(fs)} | {len({f.iati_identifier for f in fs})} | {systemic} |"
            )
        lines.append("")

    lines += ["## Samples", ""]
    for code in sorted(by_rule, key=lambda c: -len(by_rule[c])):
        fs = by_rule[code]
        label = rule_titles.get(code, fs[0].message[:70])
        lines += [f"### {code} — {label} ({len(fs)})", ""]
        for f in fs[:SAMPLES_PER_RULE]:
            lines.append(f"- [{f.iati_identifier}]({f.urls.get('d_portal', '')}) — {f.message}")
        lines.append("")
    return "\n".join(lines)


def write_reports(
    findings: list[Finding],
    rules: list[RuleSpec],
    org_id: str,
    activity_count: int,
    out_dir: Path,
    validator_reports: list[dict[str, Any]] | None = None,
    known_identifiers: set[str] | None = None,
) -> dict[str, Path]:
    validator_reports = validator_reports or []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": out_dir / "report.json",
        "csv": out_dir / "findings.csv",
        "summary": out_dir / "summary.md",
    }
    write_report_json(
        build_report(
            findings, rules, org_id, activity_count, validator_reports, known_identifiers
        ),
        paths["report"],
    )
    write_findings_csv(findings, paths["csv"])
    paths["summary"].write_text(
        build_summary(
            findings, rules, org_id, activity_count, validator_reports, known_identifiers
        ),
        encoding="utf-8",
    )
    return paths


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    totals = Counter(f.severity for f in findings)
    return {s.value: totals.get(s, 0) for s in SEVERITY_ORDER if totals.get(s, 0) or s != Severity.CRITICAL}
