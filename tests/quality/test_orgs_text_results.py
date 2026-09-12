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


def test_e_g01_non_numeric_values():
    a = make_activity(
        raw={
            "result_indicator_measure": ["1", "2"],
            "result_indicator_baseline_value": ["0", "n/a"],
            "result_indicator_period_actual_value": ["12", "twelve", "13"],
        }
    )
    issues = run("E-G01", a)
    assert {i.evidence["field"] for i in issues} == {"baseline", "actual"}


def test_e_g01_skipped_for_qualitative_measures():
    a = make_activity(
        raw={"result_indicator_measure": ["5"], "result_indicator_period_actual_value": ["done"]}
    )
    assert run("E-G01", a) == []


def test_e_g02_period_end_before_start():
    a = make_activity(
        raw={
            "result_indicator_period_period_start_iso_date": ["2025-01-01T00:00:00Z"],
            "result_indicator_period_period_end_iso_date": ["2024-01-01T00:00:00Z"],
        }
    )
    assert len(run("E-G02", a)) == 1


def test_w_g03_closed_without_results():
    assert len(run("W-G03", make_activity(status="3"))) == 1
    assert run("W-G03", make_activity(status="3", raw={"result_type": ["1"]})) == []


def test_w_g04_closed_targets_without_actuals():
    a = make_activity(status="4", raw={"result_indicator_period_target_value": ["10"]})
    assert len(run("W-G04", a)) == 1


def test_e_g05_missing_baseline_value():
    a = make_activity(
        raw={"result_indicator_measure": ["1", "2"], "result_indicator_baseline_value": ["10"]}
    )
    issues = run("E-G05", a)
    assert len(issues) == 1
    assert issues[0].evidence["present"] == 1
    assert issues[0].evidence["expected"] == 2


def test_e_g05_all_baselines_present_ok():
    a = make_activity(
        raw={"result_indicator_measure": ["1", "2"], "result_indicator_baseline_value": ["10", "20"]}
    )
    assert run("E-G05", a) == []


def test_e_g05_skipped_for_qualitative():
    assert run("E-G05", make_activity(raw={"result_indicator_measure": ["5"]})) == []


def test_w_g06_qualitative_with_value():
    a = make_activity(
        raw={"result_indicator_measure": ["5"], "result_indicator_baseline_value": ["some text"]}
    )
    issues = run("W-G06", a)
    assert len(issues) == 1
    assert issues[0].evidence["field"] == "baseline"


def test_w_g06_qualitative_without_value_ok():
    assert run("W-G06", make_activity(raw={"result_indicator_measure": ["5"]})) == []


def test_w_g06_skipped_for_mixed_measures():
    a = make_activity(
        raw={"result_indicator_measure": ["1", "5"], "result_indicator_baseline_value": ["x"]}
    )
    assert run("W-G06", a) == []
