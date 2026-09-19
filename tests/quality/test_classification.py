from iati_scout.quality.model import RecipientCountry, RecipientRegion, Sector
from tests.quality.conftest import make_activity, run


def test_e_c04_country_and_region_without_percentages():
    a = make_activity(
        recipient_countries=[RecipientCountry("KE", None)],
        recipient_regions=[RecipientRegion("1", "298", None)],
    )
    assert len(run("E-C04", a)) == 1


def test_e_c04_country_and_region_with_percentages_ok():
    a = make_activity(
        recipient_countries=[RecipientCountry("KE", 50.0)],
        recipient_regions=[RecipientRegion("1", "298", 50.0)],
    )
    assert run("E-C04", a) == []


def test_e_c05_zero_percentages():
    a = make_activity(
        sectors=[Sector("1", "15110", 0.0), Sector("1", "15150", 100.0)],
        recipient_countries=[RecipientCountry("KE", 0.0), RecipientCountry("UG", 100.0)],
    )
    assert len(run("E-C05", a)) == 2


def test_w_c06_gender_sector_without_marker():
    a = make_activity(sectors=[Sector("1", "15170", 100.0)], policy_markers={"1": "0"})
    assert len(run("W-C06", a)) == 1
    a = make_activity(sectors=[Sector("1", "15170", 100.0)], policy_markers={})
    assert len(run("W-C06", a)) == 1


def test_w_c06_gender_sector_with_marker_ok():
    a = make_activity(sectors=[Sector("1", "15170", 100.0)], policy_markers={"1": "2"})
    assert run("W-C06", a) == []


def test_w_c07_gender_principal_without_sector():
    a = make_activity(policy_markers={"1": "2"})
    assert len(run("W-C07", a)) == 1


def test_w_c08_home_country_recipient():
    a = make_activity(recipient_countries=[RecipientCountry("NL", 100.0)])
    assert len(run("W-C08", a)) == 1


def test_w_c09_humanitarian_absent():
    assert len(run("W-C09", make_activity(humanitarian=None))) == 1
    assert run("W-C09", make_activity(humanitarian=False)) == []


def test_w_c10_missing_defaults():
    a = make_activity(default_flow_type=None, default_aid_types=[])
    issues = run("W-C10", a)
    assert len(issues) == 1
    assert issues[0].evidence["missing"] == ["default-flow-type", "default-aid-type"]

