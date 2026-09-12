from iati_scout.quality.model import RecipientCountry, RecipientRegion, Sector
from tests.quality.conftest import make_activity, run


def test_e_c01_dac_percentages_not_100():
    a = make_activity(sectors=[Sector("1", "15110", 60.0), Sector("1", "15150", 30.0)])
    issues = run("E-C01", a)
    assert len(issues) == 1
    assert issues[0].evidence["sum"] == 90.0


def test_e_c01_single_sector_without_percentage_ok():
    a = make_activity(sectors=[Sector("1", "15110", None)])
    assert run("E-C01", a) == []


def test_w_c02_other_vocab_percentages():
    a = make_activity(sectors=[Sector("1", "15110", 100.0), Sector("7", "1", 1.0), Sector("7", "5", 1.0)])
    issues = run("W-C02", a)
    assert len(issues) == 1
    assert issues[0].evidence["vocabulary"] == "7"
    assert run("E-C01", a) == []


def test_e_c03_country_percentages_not_100():
    a = make_activity(recipient_countries=[RecipientCountry("KE", 50.0), RecipientCountry("UG", 30.0)])
    assert len(run("E-C03", a)) == 1


def test_e_c03_missing_percentage_multi_country():
    a = make_activity(recipient_countries=[RecipientCountry("KE", 50.0), RecipientCountry("UG", None)])
    issues = run("E-C03", a)
    assert len(issues) == 1
    assert "missing" in issues[0].message


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


def test_e_c11_missing_percentage_among_multiple_sectors():
    a = make_activity(sectors=[Sector("1", "15110", 100.0), Sector("1", "15150", None)])
    issues = run("E-C11", a)
    assert len(issues) == 1
    assert "missing" in issues[0].message


def test_e_c11_single_sector_invalid_percentage():
    assert len(run("E-C11", make_activity(sectors=[Sector("1", "15110", 60.0)]))) == 1


def test_e_c11_single_sector_omitted_or_100_ok():
    assert run("E-C11", make_activity(sectors=[Sector("1", "15110", None)])) == []
    assert run("E-C11", make_activity(sectors=[Sector("1", "15110", 100.0)])) == []


def test_e_c12_single_country_invalid_percentage():
    a = make_activity(recipient_countries=[RecipientCountry("KE", 60.0)])
    assert len(run("E-C12", a)) == 1


def test_e_c12_single_country_100_ok():
    a = make_activity(recipient_countries=[RecipientCountry("KE", 100.0)])
    assert run("E-C12", a) == []


def test_e_c13_region_missing_percentage_among_multiple():
    a = make_activity(
        recipient_regions=[RecipientRegion("1", "298", 50.0), RecipientRegion("1", "289", None)]
    )
    assert len(run("E-C13", a)) == 1


def test_e_c13_single_region_invalid_percentage():
    a = make_activity(recipient_regions=[RecipientRegion("1", "298", 60.0)])
    assert len(run("E-C13", a)) == 1


def test_e_c13_single_region_omitted_or_100_ok():
    assert run("E-C13", make_activity(recipient_regions=[RecipientRegion("1", "298", None)])) == []
    assert run("E-C13", make_activity(recipient_regions=[RecipientRegion("1", "298", 100.0)])) == []


def test_e_c14_region_percentages_not_100():
    a = make_activity(
        recipient_regions=[RecipientRegion("1", "298", 50.0), RecipientRegion("1", "289", 40.0)]
    )
    issues = run("E-C14", a)
    assert len(issues) == 1
    assert issues[0].evidence["sum"] == 90.0


def test_e_c14_region_percentages_100_ok():
    a = make_activity(
        recipient_regions=[RecipientRegion("1", "298", 60.0), RecipientRegion("1", "289", 40.0)]
    )
    assert run("E-C14", a) == []


def test_e_c15_default_language_missing_title():
    a = make_activity(
        default_language=None,
        raw={
            "title_narrative": ["Title"],
            "title_narrative_xml_lang": [],
            "description_narrative_xml_lang": ["en"],
        },
    )
    issues = run("E-C15", a)
    assert len(issues) == 1
    assert "title" in issues[0].message


def test_e_c15_default_language_missing_description():
    a = make_activity(
        default_language=None,
        raw={
            "title_narrative": ["Title"],
            "title_narrative_xml_lang": ["en"],
            "description_narrative_xml_lang": [],
        },
    )
    issues = run("E-C15", a)
    assert len(issues) == 1
    assert "description" in issues[0].message


def test_e_c15_default_language_present_ok():
    assert run("E-C15", make_activity(default_language="en")) == []
