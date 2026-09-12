from iati_scout.quality.model import ParticipatingOrg, RelatedActivityRef
from tests.quality.conftest import ORG, make_activity, run


def test_e_h01_activity_id_equals_reporting_org():
    a = make_activity(identifier=ORG)
    issues = run("E-H01", a)
    assert len(issues) == 1


def test_e_h01_different_ids_ok():
    assert run("E-H01", make_activity(identifier=f"{ORG}-ABC")) == []


def test_w_h02_activity_id_missing_prefix():
    a = make_activity(identifier="WRONG-PREFIX-1")
    issues = run("W-H02", a)
    assert len(issues) == 1


def test_w_h02_activity_id_with_prefix_ok():
    assert run("W-H02", make_activity(identifier=f"{ORG}-ABC")) == []


def test_w_h03_whitespace_in_identifier():
    a = make_activity(identifier=f"{ORG}-ABC ")
    issues = run("W-H03", a)
    assert len(issues) == 1
    assert issues[0].evidence["field"] == "iati-identifier"


def test_w_h03_whitespace_in_related_activity_ref():
    a = make_activity(related=[RelatedActivityRef(ref=" REL-1", type="1")])
    issues = run("W-H03", a)
    assert any(i.evidence["field"] == "related-activity/@ref" for i in issues)


def test_w_h03_no_whitespace_ok():
    assert run("W-H03", make_activity()) == []


def test_w_h04_forbidden_symbol_in_participating_org_ref():
    a = make_activity(
        participating_orgs=[ParticipatingOrg(ref="XM-DAC-7/1", name="Funder", role="1", type="10")]
    )
    issues = run("W-H04", a)
    assert len(issues) == 1
    assert issues[0].evidence["field"] == "participating-org/@ref"


def test_w_h04_no_forbidden_symbol_ok():
    assert run("W-H04", make_activity()) == []
