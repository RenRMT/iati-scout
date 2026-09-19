"""Export findings/rules/activities for the (separate) dashboard layer.

This is the *contract* between the Python analysis code and the Observable
Framework dashboard in `dashboard/`: the dashboard reads only the files
written here (never `iati_scout` itself), so this module is the one place
that decides what shape those files take.

Layout written under `<out_dir>/export/`:

- `meta.json`      — run metadata (org, timestamps, tool version, counts)
- `rules.json`     — the rule catalogue behind the findings: scout rules from
                      the registry, plus every official validator rule id that
                      actually appears in the fetched report
- `summary.json`   — pre-aggregated counts (totals, per rule, per section, per
                      severity, per category, per source) so the dashboard
                      doesn't need to scan `findings.parquet` for its overview
- `activities.json`— one row per activity: identity, key dates, and its own
                      per-severity and per-source counts
- `findings.parquet` — one row per finding, columnar, for DuckDB-WASM
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from iati_scout import __version__
from iati_scout.quality.findings import (
    SEVERITY_ORDER,
    Finding,
    Source,
    d_portal_activity_url,
)
from iati_scout.quality.model import Dataset
from iati_scout.quality.registry import RuleConfig, RuleSpec

SCHEMA_VERSION = 2

FINDINGS_SCHEMA = pa.schema(
    [
        pa.field("code", pa.string()),  # validator rule id ("7.5.3") or scout code ("W-B12")
        pa.field("severity", pa.string()),  # critical | error | warning | advisory
        pa.field("category", pa.string()),  # official category vocabulary
        pa.field("source", pa.string()),  # "validator" | "scout"
        pa.field("systemic", pa.bool_()),
        pa.field("iati_identifier", pa.string()),
        pa.field("message", pa.string()),
        pa.field("context", pa.string()),  # validator context lines, newline-joined
        pa.field("evidence", pa.string()),  # JSON-encoded dict (scout only)
        pa.field("item", pa.string()),  # JSON-encoded dict, or null
        pa.field("item_kind", pa.string()),  # "transaction" | "budget" | null
        pa.field("item_index", pa.int64()),  # null when `item` is null
        pa.field("related_ids", pa.list_(pa.string())),
    ]
)


def _write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _finding_row(finding: Finding) -> dict[str, Any]:
    data = finding.to_dict()
    item = data["item"]
    return {
        "code": data["code"],
        "severity": data["severity"],
        "category": data["category"],
        "source": data["source"],
        "systemic": data["systemic"],
        "iati_identifier": data["iati_identifier"],
        "message": data["message"],
        "context": "\n".join(c.get("text", "") for c in data["context"]),
        "evidence": json.dumps(data["evidence"], ensure_ascii=False),
        "item": json.dumps(item, ensure_ascii=False) if item else None,
        "item_kind": item.get("kind") if item else None,
        "item_index": item.get("index") if item else None,
        "related_ids": [r["identifier"] for r in data["related"]],
    }


def _write_findings_parquet(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_finding_row(f) for f in findings]
    table = pa.Table.from_pylist(rows, schema=FINDINGS_SCHEMA)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp_path, compression="zstd")
    tmp_path.replace(path)


def _build_rules_json(
    rules: list[RuleSpec], config: RuleConfig, findings: list[Finding]
) -> dict[str, Any]:
    """The catalogue of every rule that produced a row, from both sources.

    Scout rules are known up front from the registry. Validator rules are not:
    IATI's ruleset is versioned independently, so the only reliable catalogue
    is the set of rule ids that actually appear in the fetched report, with the
    message the validator itself supplied as the title.
    """
    catalogue = [
        {
            "code": spec.code,
            "source": Source.SCOUT.value,
            "section": spec.section,
            "category": spec.category.value,
            "severity": spec.severity.value,
            "weight": spec.weight,
            "title": spec.title,
            "description": spec.description,
            "systemic": config.is_systemic(spec.code),
            "enabled": config.is_enabled(spec.code),
        }
        for spec in rules
    ]
    seen: dict[str, Finding] = {}
    for finding in findings:
        if finding.source == Source.VALIDATOR:
            seen.setdefault(finding.code, finding)
    catalogue += [
        {
            "code": code,
            "source": Source.VALIDATOR.value,
            "section": None,
            "category": finding.category.value,
            "severity": finding.severity.value,
            "weight": finding.severity.value,
            "title": finding.message,
            "description": "",
            "systemic": False,
            "enabled": True,
        }
        for code, finding in sorted(seen.items())
    ]
    return {"thresholds": config.thresholds, "rules": catalogue}


def _build_summary_json(
    findings: list[Finding], rules: list[RuleSpec], activity_count: int
) -> dict[str, Any]:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_rule[finding.code].append(finding)

    severity_totals = Counter(f.severity.value for f in findings)
    activities_affected = len({f.iati_identifier for f in findings})
    systemic_findings = sum(1 for f in findings if f.systemic)

    # Every rule that produced a row, whichever source it came from — the
    # scout registry alone no longer covers the catalogue.
    per_rule = {
        code: {
            "findings": len(fs),
            "activities": len({f.iati_identifier for f in fs}),
            "source": fs[0].source.value,
        }
        for code, fs in by_rule.items()
    }
    for spec in rules:  # keep rules that ran but found nothing
        per_rule.setdefault(
            spec.code, {"findings": 0, "activities": 0, "source": Source.SCOUT.value}
        )

    per_category: Counter = Counter(f.category.value for f in findings)
    per_section: dict[str, Counter] = defaultdict(Counter)
    for spec in rules:
        per_section[spec.section]["findings"] += per_rule[spec.code]["findings"]
        if per_rule[spec.code]["findings"]:
            per_section[spec.section]["rules_with_findings"] += 1

    return {
        "totals": {
            "findings": len(findings),
            "activities": activity_count,
            "activities_affected": activities_affected,
            "systemic_findings": systemic_findings,
            **{s.value: severity_totals.get(s.value, 0) for s in SEVERITY_ORDER},
        },
        "per_rule": per_rule,
        "per_section": {section: dict(counts) for section, counts in per_section.items()},
        "per_severity": {s.value: severity_totals.get(s.value, 0) for s in SEVERITY_ORDER},
        "per_category": dict(per_category),
        "per_source": dict(Counter(f.source.value for f in findings)),
    }


def _build_activities_json(dataset: Dataset, findings: list[Finding]) -> list[dict[str, Any]]:
    by_severity: dict[str, Counter] = {s.value: Counter() for s in SEVERITY_ORDER}
    by_source: dict[str, Counter] = {s.value: Counter() for s in Source}
    for f in findings:
        by_severity[f.severity.value][f.iati_identifier] += 1
        by_source[f.source.value][f.iati_identifier] += 1

    def _iso(value: date | datetime | None) -> str | None:
        return value.isoformat() if value else None

    return [
        {
            "identifier": a.identifier,
            "title": a.title,
            "status": a.status,
            "hierarchy": a.hierarchy,
            "parent_id": a.parent_id,
            "planned_start": _iso(a.planned_start),
            "planned_end": _iso(a.planned_end),
            "actual_start": _iso(a.actual_start),
            "actual_end": _iso(a.actual_end),
            "last_updated": _iso(a.last_updated),
            **{s.value: by_severity[s.value].get(a.identifier, 0) for s in SEVERITY_ORDER},
            "validator_findings": by_source[Source.VALIDATOR.value].get(a.identifier, 0),
            "scout_findings": by_source[Source.SCOUT.value].get(a.identifier, 0),
            "url_d_portal": d_portal_activity_url(a.identifier),
        }
        for a in dataset
    ]


def _build_meta_json(
    dataset: Dataset,
    rules: list[RuleSpec],
    raw_manifest: dict[str, Any] | None,
    validator_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    first = (validator_reports[0].get("report") or {}) if validator_reports else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "org_id": dataset.org_id,
        "org_name": next(
            iter(a.reporting_org_names[0] for a in dataset if a.reporting_org_names), None
        ),
        "fetched_at": raw_manifest.get("fetched_at") if raw_manifest else None,
        "checked_at": datetime.now(UTC).isoformat(),
        "tool_version": __version__,
        "activity_count": len(dataset),
        "duplicate_identifiers": sorted(dataset.duplicate_identifiers),
        "rules_run": [spec.code for spec in rules],
        # Which official ruleset the validator findings were produced against —
        # IATI versions it separately from this tool, so pinning it here is what
        # makes a past run reproducible.
        "validator": {
            "valid": all(r.get("valid", True) for r in validator_reports)
            if validator_reports
            else None,
            "iati_version": first.get("iatiVersion"),
            "api_version": first.get("apiVersion"),
            "ruleset_commit_sha": first.get("rulesetCommitSha"),
            "codelist_commit_sha": first.get("codelistCommitSha"),
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


def write_export(
    findings: list[Finding],
    rules: list[RuleSpec],
    config: RuleConfig,
    dataset: Dataset,
    out_dir: Path,
    raw_manifest: dict[str, Any] | None = None,
    validator_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """Write the dashboard export contract to `<out_dir>/export/`. Returns the paths written."""
    validator_reports = validator_reports or []
    export_dir = out_dir / "export"
    paths = {
        "meta": export_dir / "meta.json",
        "rules": export_dir / "rules.json",
        "summary": export_dir / "summary.json",
        "activities": export_dir / "activities.json",
        "findings": export_dir / "findings.parquet",
    }
    _write_json(_build_meta_json(dataset, rules, raw_manifest, validator_reports), paths["meta"])
    _write_json(_build_rules_json(rules, config, findings), paths["rules"])
    _write_json(_build_summary_json(findings, rules, len(dataset)), paths["summary"])
    _write_json(_build_activities_json(dataset, findings), paths["activities"])
    _write_findings_parquet(findings, paths["findings"])
    return paths
