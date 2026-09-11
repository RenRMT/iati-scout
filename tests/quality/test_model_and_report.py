import json
from datetime import date
from pathlib import Path

from iati_scout.quality.findings import Severity, d_portal_activity_url
from iati_scout.quality.model import load_dataset
from iati_scout.quality.registry import RuleConfig, all_rules, load_rule_config
from iati_scout.quality.report import write_reports
from iati_scout.quality.runner import run_checks, select_rules


def _write_jsonl(path: Path, docs: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")


def _org_dir(tmp_path: Path) -> Path:
    org = tmp_path / "XX-TEST-1"
    org.mkdir()
    _write_jsonl(
        org / "activity.jsonl",
        [
            {
                "iati_identifier": "XX-TEST-1-P",
                "title_narrative": ["Parent"],
                "hierarchy": 1,
                "activity_status_code": "2",
                "default_currency": "EUR",
                "activity_date_type": ["1", "2"],
                "activity_date_iso_date": ["2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z"],
                "last_updated_datetime": "2026-01-01T00:00:00Z",
                "reporting_org_ref": "XX-TEST-1",
                "reporting_org_narrative": ["Test Org"],
                "sector_vocabulary": ["1"],
                "sector_code": ["15110"],
                "sector_percentage": [100.0],
                "recipient_country_code": ["KE"],
                "participating_org_ref": ["XM-DAC-7"],
                "participating_org_narrative": ["Funder", "Unref'd"],
                "participating_org_role": ["1", "4"],
                "participating_org_type": ["10", "22"],
                "humanitarian": False,
            },
            {
                "iati_identifier": "XX-TEST-1-C",
                "title_narrative": ["Child"],
                "hierarchy": 2,
                "activity_status_code": "3",
                "default_currency": "EUR",
                "activity_date_type": ["2", "4"],
                "activity_date_iso_date": ["2021-01-01T00:00:00Z", "2020-06-01T00:00:00Z"],
                "last_updated_datetime": "2026-01-01T00:00:00Z",
                "reporting_org_ref": "XX-TEST-1",
                "reporting_org_narrative": ["Test Org"],
                "related_activity_ref": ["XX-TEST-1-P"],
                "related_activity_type": ["1"],
                "humanitarian": False,
            },
            # duplicate of the child, older
            {
                "iati_identifier": "XX-TEST-1-C",
                "title_narrative": ["Child (old)"],
                "hierarchy": 2,
                "activity_status_code": "2",
                "default_currency": "EUR",
                "last_updated_datetime": "2025-01-01T00:00:00Z",
                "reporting_org_ref": "XX-TEST-1",
                "humanitarian": False,
            },
        ],
    )
    _write_jsonl(
        org / "transaction.jsonl",
        [
            {
                "iati_identifier": "XX-TEST-1-C",
                "default_currency": "EUR",
                "transaction_transaction_type_code": ["2"],
                "transaction_transaction_date_iso_date": ["2021-02-01T00:00:00Z"],
                "transaction_value_value_date": ["2021-02-01T00:00:00Z"],
                "transaction_value": [100.0],
                "transaction_receiver_org_narrative": ["NGO"],
                "transaction_receiver_org_type": ["22"],
            },
            {
                "iati_identifier": "XX-TEST-1-C",
                "default_currency": "EUR",
                "transaction_transaction_type_code": ["3"],
                "transaction_transaction_date_iso_date": ["2021-03-01T00:00:00Z"],
                "transaction_value_value_date": ["2021-03-01T00:00:00Z"],
                "transaction_value": [100.0],
                "transaction_receiver_org_narrative": ["NGO"],
                "transaction_receiver_org_type": ["22"],
            },
        ],
    )
    _write_jsonl(
        org / "budget.jsonl",
        [
            {
                "iati_identifier": "XX-TEST-1-C",
                "default_currency": "EUR",
                "budget_type": ["1"],
                "budget_status": ["2"],
                "budget_period_start_iso_date": ["2021-01-01T00:00:00Z"],
                "budget_period_end_iso_date": ["2021-12-31T00:00:00Z"],
                "budget_value": [100.0],
                "budget_value_value_date": ["2021-01-01T00:00:00Z"],
            }
        ],
    )
    return org


def test_load_dataset_links_and_dedupes(tmp_path):
    ds = load_dataset(_org_dir(tmp_path), "XX-TEST-1", today=date(2026, 9, 11))
    assert len(ds) == 2
    child = ds.get("XX-TEST-1-C")
    parent = ds.get("XX-TEST-1-P")
    assert child.title == "Child"  # newest document kept
    assert child.parent_id == "XX-TEST-1-P"
    assert parent.child_ids == ["XX-TEST-1-C"]
    assert child.actual_start == date(2021, 1, 1)
    assert [t.type for t in child.transactions] == ["2", "3"]
    assert child.budgets[0].value == 100.0
    assert child.sum_transactions("3") == 100.0
    assert "XX-TEST-1-C" in ds.duplicate_identifiers
    assert len(parent.participating_orgs) == 2
    assert parent.participating_orgs[1].ref is None


def test_run_checks_and_reports(tmp_path):
    ds = load_dataset(_org_dir(tmp_path), "XX-TEST-1", today=date(2026, 9, 11))
    config = RuleConfig(systemic={"W-C09": True})
    rules = select_rules(config)
    findings = run_checks(ds, config, rules)
    codes = {f.code for f in findings}
    assert {"E-A01", "E-D05", "W-E04"} <= codes

    out = tmp_path / "quality"
    paths = write_reports(findings, rules, "XX-TEST-1", len(ds), out)
    assert paths["jsonl"].exists() and paths["csv"].exists() and paths["summary"].exists()

    lines = paths["jsonl"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(findings)
    first = json.loads(lines[0])
    assert first["urls"]["d_portal"].startswith("https://d-portal.iatistandard.org/")

    summary = paths["summary"].read_text(encoding="utf-8")
    assert "| E-A01 |" in summary
    assert "ctrack.html#view=act&aid=XX-TEST-1-C" in summary


def test_select_rules_filters():
    config = RuleConfig(enabled={"W-C09": False})
    codes = {r.code for r in select_rules(config)}
    assert "W-C09" not in codes
    assert "E-A01" in codes

    only = select_rules(config, codes=["W-C09", "E-A01"])
    assert {r.code for r in only} == {"W-C09", "E-A01"}  # explicit list overrides disabled

    errors = select_rules(config, severity=Severity.ERROR)
    assert all(r.severity == Severity.ERROR for r in errors)

    try:
        select_rules(config, codes=["X-Z99"])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "X-Z99" in str(exc)


def test_load_rule_config(tmp_path):
    path = tmp_path / "rules.toml"
    path.write_text(
        '[thresholds]\nstale_months = 6\n[rules."E-A01"]\nenabled = false\n'
        '[rules."W-C09"]\nsystemic = true\n',
        encoding="utf-8",
    )
    config = load_rule_config(path)
    assert config.thresholds["stale_months"] == 6
    assert config.thresholds["budget_max_days"] == 366  # default preserved
    assert not config.is_enabled("E-A01")
    assert config.is_systemic("W-C09")
    assert config.is_enabled("E-A02")


def test_d_portal_url_encodes_unsafe_characters():
    assert d_portal_activity_url("XX-1-A B&C") == (
        "https://d-portal.iatistandard.org/ctrack.html#view=act&aid=XX-1-A%20B%26C"
    )


def test_every_rule_has_a_test_module():
    # Guard against adding a rule without covering it: each code must appear in tests/quality.
    tests_dir = Path(__file__).parent
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in tests_dir.glob("test_*.py"))
    missing = [r.code for r in all_rules() if f'"{r.code}"' not in corpus]
    assert missing == []
