import json
from datetime import date

import pyarrow.parquet as pq

from iati_scout.quality.export import SCHEMA_VERSION, write_export
from iati_scout.quality.registry import RuleConfig
from iati_scout.quality.runner import run_checks, select_rules

from .conftest import make_activity, make_dataset


def _dataset_with_findings():
    # actual end before actual start -> E-A01 (error); status Implementation
    # but planned end long passed -> W-A07 (warning).
    activity = make_activity(
        status="2",
        dates={
            "1": date(2020, 1, 1),
            "2": date(2020, 5, 4),
            "3": date(2021, 12, 31),
            "4": date(2020, 3, 24),
        },
    )
    ds = make_dataset(activity)
    config = RuleConfig(systemic={"E-A01": True})
    rules = select_rules(config)
    findings = run_checks(ds, config, rules)
    return ds, config, rules, findings


def test_write_export_files(tmp_path):
    ds, config, rules, findings = _dataset_with_findings()
    paths = write_export(findings, rules, config, ds, tmp_path, raw_manifest={"fetched_at": "2026-01-01T00:00:00Z"})

    assert set(paths) == {"meta", "rules", "summary", "activities", "findings"}
    for p in paths.values():
        assert p.exists()
    assert paths["meta"].parent.name == "export"

    meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["org_id"] == ds.org_id
    assert meta["fetched_at"] == "2026-01-01T00:00:00Z"
    assert meta["activity_count"] == len(ds)
    assert meta["rules_run"] == [r.code for r in rules]

    rules_json = json.loads(paths["rules"].read_text(encoding="utf-8"))
    codes = {r["code"] for r in rules_json["rules"]}
    assert "E-A01" in codes
    e_a01 = next(r for r in rules_json["rules"] if r["code"] == "E-A01")
    assert e_a01["severity"] == "error"
    assert e_a01["systemic"] is True
    assert "thresholds" in rules_json

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["totals"]["findings"] == len(findings)
    assert summary["totals"]["errors"] + summary["totals"]["warnings"] == len(findings)
    assert summary["per_rule"]["E-A01"]["findings"] == 1
    assert summary["per_rule"]["E-A01"]["activities"] == 1

    activities = json.loads(paths["activities"].read_text(encoding="utf-8"))
    assert len(activities) == len(ds)
    row = next(a for a in activities if a["identifier"] == "XX-TEST-1-A")
    assert row["errors"] >= 1
    assert row["url_d_portal"].startswith("https://d-portal.iatistandard.org/")


def test_findings_parquet_round_trips(tmp_path):
    ds, config, rules, findings = _dataset_with_findings()
    paths = write_export(findings, rules, config, ds, tmp_path)

    table = pq.read_table(paths["findings"])
    assert table.num_rows == len(findings)
    assert set(table.column_names) >= {
        "code",
        "severity",
        "systemic",
        "iati_identifier",
        "message",
        "evidence",
        "item",
        "item_kind",
        "item_index",
        "related_ids",
    }

    rows = table.to_pylist()
    e_a01 = next(r for r in rows if r["code"] == "E-A01")
    assert e_a01["severity"] == "error"
    assert e_a01["systemic"] is True
    assert e_a01["iati_identifier"] == "XX-TEST-1-A"
    evidence = json.loads(e_a01["evidence"])
    assert evidence["actual_start"] == "2020-05-04"
    assert e_a01["item"] is None
    assert e_a01["item_kind"] is None


def test_export_item_locator_for_row_level_finding(tmp_path):
    # A budget-level rule (E-B01: period end before start) carries an `item` locator.
    from .conftest import make_budget

    activity = make_activity(
        budgets=[make_budget(start=date(2025, 6, 1), end=date(2025, 1, 1))]
    )
    ds = make_dataset(activity)
    config = RuleConfig()
    rules = select_rules(config, codes=["E-B01"])
    findings = run_checks(ds, config, rules)
    assert len(findings) == 1

    paths = write_export(findings, rules, config, ds, tmp_path)
    table = pq.read_table(paths["findings"]).to_pylist()
    row = table[0]
    assert row["item_kind"] == "budget"
    assert row["item_index"] == 0
    item = json.loads(row["item"])
    assert item["period_start"] == "2025-06-01"
