from iati_scout.quality.model import ParticipatingOrg, RecipientCountry
from tests.quality.conftest import make_activity, run

# --- E: organisations ------------------------------------------------------


def test_e_e01_missing_funding_and_accountable():
    a = make_activity(participating_orgs=[ParticipatingOrg("X", "Impl", "4", "22")])
    issues = run("E-E01", a)
    assert {i.evidence["missing_role"] for i in issues} == {"1", "2"}


def test_w_e02_missing_implementing():
    a = make_activity(
        participating_orgs=[
            ParticipatingOrg("F", "Funder", "1", "10"),
            ParticipatingOrg("A", "Acc", "2", "10"),
        ]
    )
    assert len(run("W-E02", a)) == 1


def test_w_e03_duplicate_org_same_role():
    a = make_activity(
        participating_orgs=[
            ParticipatingOrg("F", "Funder", "1", "10"),
            ParticipatingOrg("A", "Acc", "2", "10"),
            ParticipatingOrg("X", "Local NGO", "4", "22"),
            ParticipatingOrg("X", "local ngo", "4", "22"),
        ]
    )
    issues = run("W-E03", a)
    assert len(issues) == 1
    assert issues[0].evidence["count"] == 2


def test_w_e04_org_without_ref():
    a = make_activity(
        raw={"participating_org_ref": ["F"], "participating_org_narrative": ["Funder", "NoRef"]}
    )
    assert len(run("W-E04", a)) == 1


def test_w_e05_org_type_other():
    a = make_activity(participating_orgs=[ParticipatingOrg("F", "Funder", "1", "90")])
    assert len(run("W-E05", a)) == 1


# --- F: text & location ----------------------------------------------------


def test_e_f01_malformed_pos():
    a = make_activity(location_positions=["4.624.335 -74.063.644", "abc"])
    assert len(run("E-F01", a)) == 2


def test_e_f02_out_of_range_and_null_island():
    a = make_activity(location_positions=["0 0", "95.0 10.0", "10.0 -190.0", "52.0 4.0"])
    assert len(run("E-F02", a)) == 3


def test_w_f03_location_in_home_country():
    a = make_activity(location_positions=["52.07 4.27"], recipient_countries=[RecipientCountry("KE", 100.0)])
    assert len(run("W-F03", a)) == 1
    a = make_activity(location_positions=["52.07 4.27"], recipient_countries=[RecipientCountry("NL", 100.0)])
    assert run("W-F03", a) == []


def test_w_f04_title_quality():
    assert len(run("W-F04", make_activity(title="Short"))) == 1
    assert len(run("W-F04", make_activity(title="ALL CAPS TITLE HERE"))) == 1
    assert len(run("W-F04", make_activity(title="  Leading  and double  "))) == 1


def test_w_f05_description_quality():
    assert len(run("W-F05", make_activity(descriptions=["Too short"]))) == 1
    same = "Same text used for both the title and the description"
    a = make_activity(title=same, descriptions=[same])
    assert len(run("W-F05", a)) == 1
    a = make_activity(descriptions=["x" * 255])
    assert len(run("W-F05", a)) == 1
    a = make_activity(descriptions=["A description that trails off into nothing much at all..."])
    assert len(run("W-F05", a)) == 1


# --- G: results ------------------------------------------------------------


def test_w_g03_closed_without_results():
    assert len(run("W-G03", make_activity(status="3"))) == 1
    assert run("W-G03", make_activity(status="3", raw={"result_type": ["1"]})) == []


def test_w_g04_closed_targets_without_actuals():
    a = make_activity(status="4", raw={"result_indicator_period_target_value": ["10"]})
    assert len(run("W-G04", a)) == 1

