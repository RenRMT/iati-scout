"""Cross-cutting checks: every rule has a code in the expected format, a clean
activity triggers nothing, and every emitted Finding is self-contained."""

import re

from iati_scout.quality.findings import Category, Finding, Severity, Source
from iati_scout.quality.registry import SECTION_CATEGORIES, Context, all_rules
from iati_scout.quality.runner import run_rule
from tests.quality.conftest import make_activity, make_dataset

CODE_RE = re.compile(r"^[EW]-[A-H]\d{2}$")


def test_every_rule_is_advisory_with_a_valid_category():
    """Scout rules never claim an IATI severity: they are heuristics, not standard violations."""
    for spec in all_rules():
        assert CODE_RE.match(spec.code), spec.code
        assert spec.severity == Severity.ADVISORY, spec.code
        assert isinstance(spec.category, Category), spec.code
        # Section F splits between geo and information; every other section is fixed.
        if spec.section != "F":
            assert spec.category == SECTION_CATEGORIES[spec.section], spec.code
        else:
            assert spec.category in (Category.GEO, Category.INFORMATION), spec.code
        assert spec.weight == ("error" if spec.code.startswith("E-") else "warning")
        assert spec.title


def test_no_rule_duplicates_the_official_ruleset():
    """The official IATI ruleset is fetched, not re-implemented.

    These codes were removed when `iati-scout` switched to the IATI Validator
    report as its source for standard-ruleset checks; reintroducing one would
    mean the same violation is reported twice, from two sources that can drift.
    """
    removed = {
        "E-A01", "E-A02", "E-A03", "E-A10", "E-A11",
        "E-B01", "E-B04", "E-B22", "E-B23", "E-B24",
        "E-C01", "W-C02", "E-C03", "E-C11", "E-C12", "E-C13", "E-C14", "E-C15",
        "E-G01", "E-G02", "E-G05", "W-G06",
        "E-H01", "W-H02", "W-H03", "W-H04",
    }
    assert {spec.code for spec in all_rules()} & removed == set()


def test_clean_activity_triggers_no_rule():
    activity = make_activity()
    ds = make_dataset(activity)
    ctx = Context(dataset=ds)
    triggered = {spec.code for spec in all_rules() if list(spec.func(activity, ctx))}
    assert triggered == set()


def test_findings_are_self_contained():
    # An activity that violates a handful of rules across sections.
    from datetime import date

    from tests.quality.conftest import make_budget, make_txn

    activity = make_activity(
        status="3",
        dates={"2": date(2024, 1, 15), "4": date(2023, 1, 1)},
        transactions=[make_txn(type="3", value=-5.0, receiver_type="90")],
        budgets=[make_budget(start=date(2025, 6, 1), end=date(2025, 1, 1), value=-1.0)],
        location_positions=["4.624.335 -74.063.644"],
    )
    ds = make_dataset(activity)
    ctx = Context(dataset=ds)
    findings: list[Finding] = []
    for spec in all_rules():
        findings.extend(run_rule(spec, activity, ctx, systemic=False))

    assert findings
    for f in findings:
        assert f.message and f.message.strip(), f.code
        assert isinstance(f.evidence, dict) and f.evidence, f.code
        assert f.urls["d_portal"] == (
            "https://d-portal.iatistandard.org/ctrack.html#view=act&aid=XX-TEST-1-A"
        )
        assert f.activity_title == activity.title
        assert f.source == Source.SCOUT
        assert f.context and f.context[0]["text"] == f.message
        # Serialisable (dates converted, enums to values)
        payload = f.to_dict()
        assert payload["severity"] == "advisory"
        assert payload["source"] == "scout"
        assert payload["category"] in {c.value for c in Category}
        import json

        json.dumps(payload)
        # And representable as an official validator error object.
        error = f.to_validator_error()
        assert error["id"] == f.code
        assert error["severity"] == "advisory"
        assert error["details"]["source"] == "scout"
        json.dumps(error)


def test_row_level_findings_carry_item_locator():
    from datetime import date

    from tests.quality.conftest import make_budget, make_txn

    activity = make_activity(
        transactions=[make_txn(type="3", value=-5.0)],
        budgets=[make_budget(value=-1.0)],
    )
    ds = make_dataset(activity)
    ctx = Context(dataset=ds)
    by_code = {}
    for spec in all_rules():
        for f in run_rule(spec, activity, ctx, systemic=False):
            by_code.setdefault(f.code, f)
    assert by_code["W-B08"].item["kind"] == "transaction"
    assert by_code["W-B08"].item["value"] == -5.0
    assert by_code["E-B03"].item["kind"] == "budget"
    assert by_code["E-B03"].item["period_start"] == date(2025, 1, 1).isoformat()
