"""Cross-cutting checks: every rule has a code in the expected format, a clean
activity triggers nothing, and every emitted Finding is self-contained."""

import re

from iati_scout.quality.findings import Finding, Severity
from iati_scout.quality.registry import Context, all_rules
from iati_scout.quality.runner import run_rule
from tests.quality.conftest import make_activity, make_dataset

CODE_RE = re.compile(r"^[EW]-[A-H]\d{2}$")


def test_rule_codes_and_severity_prefix_agree():
    for spec in all_rules():
        assert CODE_RE.match(spec.code), spec.code
        expected = Severity.ERROR if spec.code.startswith("E-") else Severity.WARNING
        assert spec.severity == expected, spec.code
        assert spec.title


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
        # Serialisable (dates converted, enums to values)
        payload = f.to_dict()
        assert payload["severity"] in ("error", "warning")
        import json

        json.dumps(payload)


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
