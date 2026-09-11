from datetime import date

from iati_scout.quality.model import RecipientCountry, RelatedActivityRef
from tests.quality.conftest import make_activity, run


def _parent(**overrides):
    base = {
        "identifier": "XX-TEST-1-P",
        "hierarchy": 1,
        "dates": {"1": date(2020, 1, 1), "2": date(2020, 1, 1), "3": date(2026, 12, 31)},
    }
    base.update(overrides)
    return make_activity(**base)


def _child(**overrides):
    base = {
        "identifier": "XX-TEST-1-C",
        "hierarchy": 2,
        "related": [RelatedActivityRef("XX-TEST-1-P", "1")],
        "dates": {"1": date(2021, 1, 1), "2": date(2021, 1, 1), "3": date(2025, 12, 31)},
    }
    base.update(overrides)
    return make_activity(**base)


def test_e_d01_related_not_found():
    c = _child(related=[RelatedActivityRef("XX-TEST-1-MISSING", "1")])
    issues = run("E-D01", c)
    assert len(issues) == 1
    assert issues[0].related[0].identifier == "XX-TEST-1-MISSING"
    assert issues[0].related[0].url.endswith("aid=XX-TEST-1-MISSING")


def test_e_d01_found_ok():
    p, c = _parent(), _child()
    assert run("E-D01", c, p) == []


def test_e_d02_related_to_self():
    c = _child(related=[RelatedActivityRef("XX-TEST-1-C", "3")])
    assert len(run("E-D02", c)) == 1


def test_e_d03_hierarchy_without_relations():
    assert len(run("E-D03", make_activity(hierarchy=2, related=[]))) == 1
    lonely_parent = _parent()
    assert len(run("E-D03", lonely_parent)) == 1
    p, c = _parent(), _child()
    assert run("E-D03", p, c) == []
    assert run("E-D03", c, p) == []


def test_e_d04_child_dates_outside_parent():
    p = _parent(dates={"2": date(2020, 1, 1), "4": date(2024, 1, 1)})
    c = _child(dates={"2": date(2019, 1, 1), "4": date(2025, 1, 1)})
    issues = run("E-D04", c, p)
    assert len(issues) == 2
    assert all(i.related[0].relation == "parent" for i in issues)


def test_e_d05_duplicate_identifier():
    c = _child()
    issues = run(
        "E-D05",
        c,
        duplicate_identifiers={c.identifier: [{"dataset_generated": "a"}, {"dataset_generated": "b"}]},
    )
    assert len(issues) == 1
    assert "2 times" in issues[0].message


def test_w_d05_child_planned_end_after_parent():
    p = _parent(dates={"3": date(2025, 1, 1)})
    c = _child(dates={"3": date(2026, 1, 1)})
    assert len(run("W-D05", c, p)) == 1


def test_w_d06_child_country_not_in_parent():
    p = _parent(recipient_countries=[RecipientCountry("KE", 100.0)])
    c = _child(recipient_countries=[RecipientCountry("UG", 100.0)])
    issues = run("W-D06", c, p)
    assert len(issues) == 1
    assert issues[0].evidence["child_countries_not_in_parent"] == ["UG"]


def test_w_d07_child_defaults_differ():
    p = _parent(default_flow_type="10", default_aid_types=["C01"])
    c = _child(default_flow_type="30", default_aid_types=["D02"])
    assert len(run("W-D07", c, p)) == 2


def test_w_d08_parent_closed_child_implementing():
    p = _parent(status="4")
    c = _child(status="2")
    assert len(run("W-D08", c, p)) == 1
