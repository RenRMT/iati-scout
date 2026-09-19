import json
from datetime import date
from pathlib import Path

from iati_scout.quality.findings import Category, Severity, Source, d_portal_activity_url
from iati_scout.quality.model import load_dataset
from iati_scout.quality.registry import RuleConfig, all_rules, load_rule_config
from iati_scout.quality.report import build_report, write_reports
from iati_scout.quality.runner import findings_from_reports, run_checks, select_rules

from .test_export import VALIDATOR_REPORT


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
    findings = findings_from_reports([VALIDATOR_REPORT]) + run_checks(ds, config, rules)
    codes = {f.code for f in findings}
    assert {"E-D05", "W-E04", "7.5.3"} <= codes

    out = tmp_path / "quality"
    paths = write_reports(
        findings,
        rules,
        "XX-TEST-1",
        len(ds),
        out,
        validator_reports=[VALIDATOR_REPORT],
        known_identifiers={a.identifier for a in ds},
    )
    assert paths["report"].exists() and paths["csv"].exists() and paths["summary"].exists()

    summary = paths["summary"].read_text(encoding="utf-8")
    assert "E-D05 — Activity identifier published more than once" in summary
    assert "ctrack.html#view=act&aid=XX-TEST-1-C" in summary
    # Each source gets its own table, so a reader can tell them apart at a glance.
    assert "## Official IATI validator findings" in summary
    assert "## Additional iati-scout findings" in summary


def test_report_json_matches_the_official_shape(tmp_path):
    """`report.json` must be readable by anything that reads an IATI validator report."""
    ds = load_dataset(_org_dir(tmp_path), "XX-TEST-1", today=date(2026, 9, 11))
    config = RuleConfig()
    rules = select_rules(config)
    findings = findings_from_reports([VALIDATOR_REPORT]) + run_checks(ds, config, rules)

    paths = write_reports(
        findings,
        rules,
        "XX-TEST-1",
        len(ds),
        tmp_path / "quality",
        validator_reports=[VALIDATOR_REPORT],
        known_identifiers={a.identifier for a in ds},
    )
    report = json.loads(paths["report"].read_text(encoding="utf-8"))

    assert set(report["report"]) >= {
        "valid",
        "fileType",
        "iatiVersion",
        "rulesetCommitSha",
        "codelistCommitSha",
        "apiVersion",
        "summary",
        "errors",
    }
    assert report["report"]["iatiVersion"] == "2.03"
    assert set(report["report"]["summary"]) == {"critical", "error", "warning", "advisory"}
    assert sum(report["report"]["summary"].values()) == len(findings)

    # The contract's activity -> category -> error nesting, losing nothing.
    flattened = [
        error
        for activity in report["report"]["errors"]
        for group in activity["errors"]
        for error in group["errors"]
    ]
    assert len(flattened) == len(findings)
    for activity in report["report"]["errors"]:
        assert set(activity) == {"identifier", "title", "errors"}
        for group in activity["errors"]:
            assert set(group) == {"category", "errors"}
            assert group["category"] in {c.value for c in Category}
            for error in group["errors"]:
                assert {"id", "severity", "message", "context"} <= set(error)

    # Validator findings keep their own severity and stay untouched; scout
    # findings are advisory and identify themselves through `details.source`,
    # which is needed because the validator uses `advisory` for its 1000.x rules.
    official = next(e for e in flattened if e["id"] == "7.5.3")
    assert official["severity"] == "error"
    assert "details" not in official
    scout = next(e for e in flattened if e["id"].startswith(("E-", "W-")))
    assert scout["severity"] == "advisory"
    assert scout["details"]["source"] == "scout"

    # Scout's own metadata is namespaced, never mixed into the official block.
    assert report["scout"]["org_id"] == "XX-TEST-1"
    assert report["scout"]["per_source"]["validator"] == 1
    assert report["scout"]["documents"][0]["registry_name"] == "xx-test"


def test_report_flags_activities_missing_from_the_datastore(tmp_path):
    """The validator reads published XML, so it can see activities the Datastore has not."""
    ds = load_dataset(_org_dir(tmp_path), "XX-TEST-1", today=date(2026, 9, 11))
    unknown = dict(VALIDATOR_REPORT)
    unknown["report"] = dict(VALIDATOR_REPORT["report"])
    unknown["report"]["errors"] = [
        {**VALIDATOR_REPORT["report"]["errors"][0], "identifier": "XX-TEST-1-NOT-INGESTED"}
    ]
    findings = findings_from_reports([unknown])

    report = build_report(
        findings, [], "XX-TEST-1", len(ds), [unknown], {a.identifier for a in ds}
    )
    assert report["scout"]["activities_not_in_datastore"] == ["XX-TEST-1-NOT-INGESTED"]


def test_findings_from_report_flattens_the_nesting():
    findings = findings_from_reports([VALIDATOR_REPORT])
    assert len(findings) == 1
    f = findings[0]
    assert f.code == "7.5.3"
    assert f.severity == Severity.ERROR
    assert f.category == Category.FINANCIAL
    assert f.source == Source.VALIDATOR
    assert f.iati_identifier == "XX-TEST-1-A"
    assert f.context == [{"text": "period-end at line: 49"}]
    assert f.urls["d_portal"].startswith("https://d-portal.iatistandard.org/")


def test_unknown_validator_category_or_severity_does_not_drop_the_finding():
    """IATI can extend its vocabularies without warning; an unknown value must not lose data."""
    odd = {
        "report": {
            "errors": [
                {
                    "identifier": "XX-TEST-1-A",
                    "title": "t",
                    "errors": [
                        {
                            "category": "something-new",
                            "errors": [{"id": "9.9.9", "severity": "brand-new", "message": "m"}],
                        }
                    ],
                }
            ]
        }
    }
    findings = findings_from_reports([odd])
    assert len(findings) == 1
    assert findings[0].category == Category.IATI
    assert findings[0].severity == Severity.ERROR


def test_select_rules_filters():
    config = RuleConfig(enabled={"W-C09": False})
    codes = {r.code for r in select_rules(config)}
    assert "W-C09" not in codes
    assert "E-A05" in codes

    only = select_rules(config, codes=["W-C09", "E-A05"])
    assert {r.code for r in only} == {"W-C09", "E-A05"}  # explicit list overrides disabled

    financial = select_rules(config, category=Category.FINANCIAL)
    assert financial and all(r.category == Category.FINANCIAL for r in financial)

    try:
        select_rules(config, codes=["X-Z99"])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "X-Z99" in str(exc)


def test_load_rule_config(tmp_path):
    path = tmp_path / "rules.toml"
    path.write_text(
        '[thresholds]\nstale_months = 6\n[rules."E-A05"]\nenabled = false\n'
        '[rules."W-C09"]\nsystemic = true\n',
        encoding="utf-8",
    )
    config = load_rule_config(path)
    assert config.thresholds["stale_months"] == 6
    assert config.thresholds["budget_max_days"] == 366  # default preserved
    assert not config.is_enabled("E-A05")
    assert config.is_systemic("W-C09")
    assert config.is_enabled("E-A06")


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
