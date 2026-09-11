from datetime import UTC, date, datetime

import pytest

from iati_scout.quality.findings import Issue
from iati_scout.quality.model import (
    Activity,
    Budget,
    Dataset,
    ParticipatingOrg,
    RecipientCountry,
    RelatedActivityRef,
    Sector,
    Transaction,
)
from iati_scout.quality.registry import Context, get_rule

TODAY = date(2026, 9, 11)
ORG = "XX-TEST-1"


def make_activity(identifier: str = "XX-TEST-1-A", **overrides) -> Activity:
    """A clean activity that triggers no rule; override fields per test."""
    base = {
        "identifier": identifier,
        "raw": {},
        "title": "A perfectly reasonable activity title",
        "descriptions": ["A description that is long enough to not be flagged by any rule."],
        "status": "2",
        "hierarchy": None,
        "currency": "EUR",
        "dates": {
            "1": date(2024, 1, 1),
            "2": date(2024, 1, 15),
            "3": date(2027, 12, 31),
        },
        "last_updated": datetime(2026, 6, 1, tzinfo=UTC),
        "reporting_org_ref": ORG,
        "reporting_org_names": ["Test Org"],
        "sectors": [Sector("1", "15110", 100.0), Sector("7", "16", 100.0)],
        "recipient_countries": [RecipientCountry("KE", 100.0)],
        "recipient_region_codes": [],
        "participating_orgs": [
            ParticipatingOrg("XM-DAC-7", "Funder", "1", "10"),
            ParticipatingOrg(ORG, "Test Org", "2", "10"),
            ParticipatingOrg("KE-NGO-1", "Local NGO", "4", "22"),
        ],
        "related": [],
        "policy_markers": {},
        "default_flow_type": "10",
        "default_aid_types": ["C01"],
        "default_finance_type": "110",
        "default_tied_status": "5",
        "collaboration_type": "1",
        "humanitarian": False,
        "location_positions": [],
        "transactions": [],
        "budgets": [],
    }
    base.update(overrides)
    return Activity(**base)


def make_txn(
    type: str = "3",
    value: float = 1000.0,
    on: date = date(2025, 3, 1),
    index: int = 0,
    receiver: str | None = "Local NGO",
    receiver_type: str | None = "22",
    **overrides,
) -> Transaction:
    base = {
        "index": index,
        "type": type,
        "date": on,
        "value_date": on,
        "value": value,
        "currency": "EUR",
        "ref": None,
        "provider_ref": "XM-DAC-7",
        "provider_name": "Funder",
        "receiver_ref": None,
        "receiver_name": receiver,
        "receiver_type": receiver_type,
        "humanitarian": None,
    }
    base.update(overrides)
    return Transaction(**base)


def make_budget(
    start: date = date(2025, 1, 1),
    end: date = date(2025, 12, 31),
    value: float = 1000.0,
    index: int = 0,
    **overrides,
) -> Budget:
    base = {
        "index": index,
        "type": "1",
        "status": "2",
        "period_start": start,
        "period_end": end,
        "value": value,
        "value_date": start,
        "currency": "EUR",
    }
    base.update(overrides)
    return Budget(**base)


def make_dataset(*activities: Activity, **kwargs) -> Dataset:
    ds = Dataset(
        org_id=ORG,
        activities={a.identifier: a for a in activities},
        today=TODAY,
        **kwargs,
    )
    # Resolve parent/child links the same way load_dataset does.
    for a in activities:
        for rel in a.related:
            if rel.type == "1":
                a.parent_id = rel.ref
                parent = ds.get(rel.ref)
                if parent and a.identifier not in parent.child_ids:
                    parent.child_ids.append(a.identifier)
    return ds


def run(code: str, activity: Activity, *others: Activity, **ctx_kwargs) -> list[Issue]:
    ds = make_dataset(activity, *others, **ctx_kwargs)
    ctx = Context(dataset=ds)
    return list(get_rule(code).func(activity, ctx))


@pytest.fixture
def clean_activity() -> Activity:
    return make_activity()


__all__ = [
    "ORG",
    "TODAY",
    "RelatedActivityRef",
    "make_activity",
    "make_budget",
    "make_dataset",
    "make_txn",
    "run",
]
