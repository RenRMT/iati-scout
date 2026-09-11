"""Write findings to disk: findings.jsonl (canonical), findings.csv, summary.md."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from iati_scout.quality.findings import Finding, Severity
from iati_scout.quality.registry import RuleSpec

CSV_COLUMNS = [
    "code",
    "severity",
    "rule_title",
    "iati_identifier",
    "activity_title",
    "message",
    "evidence",
    "item",
    "related",
    "d_portal_url",
    "systemic",
]

SAMPLES_PER_RULE = 3


def write_findings_jsonl(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for finding in findings:
            f.write(json.dumps(finding.to_dict(), ensure_ascii=False))
            f.write("\n")


def write_findings_csv(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for finding in findings:
            data = finding.to_dict()
            writer.writerow(
                {
                    "code": data["code"],
                    "severity": data["severity"],
                    "rule_title": data["rule_title"],
                    "iati_identifier": data["iati_identifier"],
                    "activity_title": data["activity_title"],
                    "message": data["message"],
                    "evidence": json.dumps(data["evidence"], ensure_ascii=False),
                    "item": json.dumps(data["item"], ensure_ascii=False) if data["item"] else "",
                    "related": ";".join(r["identifier"] for r in data["related"]),
                    "d_portal_url": data["urls"]["d_portal"],
                    "systemic": data["systemic"],
                }
            )


def build_summary(
    findings: list[Finding],
    rules: list[RuleSpec],
    org_id: str,
    activity_count: int,
) -> str:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.code].append(finding)
    activities_per_rule = {code: len({f.iati_identifier for f in fs}) for code, fs in by_rule.items()}
    severity_totals = Counter(f.severity for f in findings)
    affected = len({f.iati_identifier for f in findings})

    lines = [
        f"# Data-quality summary for {org_id}",
        "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} over {activity_count} activities.",
        "",
        f"- Errors: **{severity_totals.get(Severity.ERROR, 0)}**",
        f"- Warnings: **{severity_totals.get(Severity.WARNING, 0)}**",
        f"- Activities with at least one finding: **{affected}** "
        f"({affected / activity_count:.0%})" if activity_count else "",
        "",
        "## Findings per rule",
        "",
        "| Code | Severity | Rule | Findings | Activities | Systemic |",
        "|---|---|---|---:|---:|:-:|",
    ]
    for spec in rules:
        fs = by_rule.get(spec.code, [])
        systemic = "yes" if fs and fs[0].systemic else ""
        lines.append(
            f"| {spec.code} | {spec.severity.value} | {spec.title} | {len(fs)} | "
            f"{activities_per_rule.get(spec.code, 0)} | {systemic} |"
        )

    lines += ["", "## Samples", ""]
    for spec in rules:
        fs = by_rule.get(spec.code)
        if not fs:
            continue
        lines.append(f"### {spec.code} — {spec.title} ({len(fs)})")
        lines.append("")
        for f in fs[:SAMPLES_PER_RULE]:
            lines.append(f"- [{f.iati_identifier}]({f.urls['d_portal']}) — {f.message}")
        lines.append("")
    return "\n".join(lines)


def write_reports(
    findings: list[Finding],
    rules: list[RuleSpec],
    org_id: str,
    activity_count: int,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "jsonl": out_dir / "findings.jsonl",
        "csv": out_dir / "findings.csv",
        "summary": out_dir / "summary.md",
    }
    write_findings_jsonl(findings, paths["jsonl"])
    write_findings_csv(findings, paths["csv"])
    paths["summary"].write_text(
        build_summary(findings, rules, org_id, activity_count), encoding="utf-8"
    )
    return paths
