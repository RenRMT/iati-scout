import json
from datetime import date

import pyarrow.parquet as pq

from iati_scout.quality.export import SCHEMA_VERSION, write_export
from iati_scout.quality.registry import RuleConfig
from iati_scout.quality.runner import findings_from_reports, run_checks, select_rules

from .conftest import make_activity, make_dataset

# A minimal official validator report, shaped exactly like the live API's, so
# the export is exercised with findings from both sources.
VALIDATOR_REPORT = {
    "registry_name": "xx-test",
    "registry_id": "abc-123",
    "registry_hash": "deadbeef",
    "document_url": "https://example.org/iati.xml",
    "valid": True,
    "report": {
        "valid": True,
        "fileType": "iati-activities",
        "iatiVersion": "2.03",
        "apiVersion": "2.5.0",
        "rulesetCommitSha": "2cd1a14f6c",
        "codelistCommitSha": "ba76c3118d",
        "orgIdPrefixFileName": "org-id-74880323ea.json",
        "summary": {"critical": 0, "error": 1, "warning": 0, "advisory": 0},
        "errors": [
            {
                "identifier": "XX-TEST-1-A",
                "title": "Test activity",
                "errors": [
                    {
                        "category": "financial",
                        "errors": [
                            {
                                "id": "7.5.3",
                                "severity": "error",
                                "message": "Budget Period must not be longer than one year.",
                                "context": [{"text": "period-end at line: 49"}],
                            }
                        ],
                    }
                ],
            }
        ],
    },
}


def _dataset_with_findings():
    # Status Implementation (2) with an actual end date -> E-A05; planned end
    # long past -> W-A07. Both are scout rules, so both arrive as `advisory`.
    activity = make_activity(
        status="2",
        dates={
            "1": date(2020, 1, 1),
            "2": date(2020, 3, 24),
            "3": date(2021, 12, 31),
            "4": date(2022, 5, 4),
        },
    )
    ds = make_dataset(activity)
    config = RuleConfig(systemic={"E-A05": True})
    rules = select_rules(config)
    findings = findings_from_reports([VALIDATOR_REPORT]) + run_checks(ds, config, rules)
    return ds, config, rules, findings


def test_write_export_files(tmp_path):
    ds, config, rules, findings = _dataset_with_findings()
    paths = write_export(
        findings,
        rules,
        config,
        ds,
        tmp_path,
        raw_manifest={"fetched_at": "2026-01-01T00:00:00Z"},
        validator_reports=[VALIDATOR_REPORT],
    )

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
    # The official ruleset version the validator findings came from is pinned.
    assert meta["validator"]["ruleset_commit_sha"] == "2cd1a14f6c"
    assert meta["validator"]["iati_version"] == "2.03"
    assert meta["validator"]["documents"][0]["registry_name"] == "xx-test"

    rules_json = json.loads(paths["rules"].read_text(encoding="utf-8"))
    by_code = {r["code"]: r for r in rules_json["rules"]}
    assert by_code["E-A05"]["severity"] == "advisory"
    assert by_code["E-A05"]["source"] == "scout"
    assert by_code["E-A05"]["weight"] == "error"  # scout's own confidence signal
    assert by_code["E-A05"]["category"] == "iati"
    assert by_code["E-A05"]["systemic"] is True
    # Validator rules enter the catalogue from the report, not the registry.
    assert by_code["7.5.3"]["source"] == "validator"
    assert by_code["7.5.3"]["severity"] == "error"
    assert "thresholds" in rules_json

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["totals"]["findings"] == len(findings)
    assert summary["totals"]["error"] == 1
    assert summary["totals"]["advisory"] == len(findings) - 1
    assert summary["per_rule"]["E-A05"]["findings"] == 1
    assert summary["per_rule"]["E-A05"]["activities"] == 1
    assert summary["per_source"] == {"validator": 1, "scout": len(findings) - 1}
    assert summary["per_category"]["financial"] == 1

    activities = json.loads(paths["activities"].read_text(encoding="utf-8"))
    assert len(activities) == len(ds)
    row = next(a for a in activities if a["identifier"] == "XX-TEST-1-A")
    assert row["advisory"] >= 1
    assert row["error"] == 1
    assert row["validator_findings"] == 1
    assert row["scout_findings"] >= 1
    assert row["url_d_portal"].startswith("https://d-portal.iatistandard.org/")


def test_findings_parquet_round_trips(tmp_path):
    ds, config, rules, findings = _dataset_with_findings()
    paths = write_export(findings, rules, config, ds, tmp_path)

    table = pq.read_table(paths["findings"])
    assert table.num_rows == len(findings)
    assert set(table.column_names) >= {
        "code",
        "severity",
        "category",
        "source",
        "systemic",
        "iati_identifier",
        "message",
        "context",
        "evidence",
        "item",
        "item_kind",
        "item_index",
        "related_ids",
    }

    rows = table.to_pylist()
    scout = next(r for r in rows if r["code"] == "E-A05")
    assert scout["severity"] == "advisory"
    assert scout["source"] == "scout"
    assert scout["category"] == "iati"
    assert scout["systemic"] is True
    assert scout["iati_identifier"] == "XX-TEST-1-A"
    assert json.loads(scout["evidence"])["actual_end"] == "2022-05-04"
    assert scout["item"] is None
    assert scout["item_kind"] is None

    validator = next(r for r in rows if r["code"] == "7.5.3")
    assert validator["severity"] == "error"
    assert validator["source"] == "validator"
    assert validator["context"] == "period-end at line: 49"
    assert json.loads(validator["evidence"]) == {}


def test_export_item_locator_for_row_level_finding(tmp_path):
    # A budget-level rule (E-B03: negative budget value) carries an `item` locator.
    from .conftest import make_budget

    activity = make_activity(budgets=[make_budget(value=-1.0)])
    ds = make_dataset(activity)
    config = RuleConfig()
    rules = select_rules(config, codes=["E-B03"])
    findings = run_checks(ds, config, rules)
    assert len(findings) == 1

    paths = write_export(findings, rules, config, ds, tmp_path)
    table = pq.read_table(paths["findings"]).to_pylist()
    row = table[0]
    assert row["item_kind"] == "budget"
    assert row["item_index"] == 0
    item = json.loads(row["item"])
    assert item["period_start"] == "2025-01-01"
