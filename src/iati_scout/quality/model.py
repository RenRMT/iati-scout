"""Typed view over the flattened Datastore JSONL files.

The Datastore `/select` output flattens each activity into parallel arrays
(`transaction_value[i]` pairs with `transaction_transaction_type_code[i]`, etc.).
This module turns those into small dataclasses so rules can be written against
`activity.dates`, `activity.transactions`, `activity.parent`, ... instead of
index arithmetic.

Transactions and budgets are taken from the dedicated `transaction.jsonl` and
`budget.jsonl` collections (one document per row) rather than from the arrays
on the activity document, because the per-row documents are unambiguous.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# IATI ActivityDateType codes
PLANNED_START = "1"
ACTUAL_START = "2"
PLANNED_END = "3"
ACTUAL_END = "4"

# IATI ActivityStatus codes
STATUS_PIPELINE = "1"
STATUS_IMPLEMENTATION = "2"
STATUS_FINALISATION = "3"
STATUS_CLOSED = "4"
STATUS_CANCELLED = "5"
STATUS_SUSPENDED = "6"
CLOSED_STATUSES = frozenset({STATUS_FINALISATION, STATUS_CLOSED})

# IATI TransactionType codes
TXN_INCOMING_FUNDS = "1"
TXN_COMMITMENT = "2"
TXN_DISBURSEMENT = "3"
TXN_EXPENDITURE = "4"
TXN_INCOMING_COMMITMENT = "11"
OUTGOING_TXN_TYPES = frozenset({TXN_COMMITMENT, TXN_DISBURSEMENT, TXN_EXPENDITURE})
INCOMING_TXN_TYPES = frozenset({TXN_INCOMING_FUNDS, TXN_INCOMING_COMMITMENT})

# IATI OrganisationRole codes
ROLE_FUNDING = "1"
ROLE_ACCOUNTABLE = "2"
ROLE_EXTENDING = "3"
ROLE_IMPLEMENTING = "4"

# IATI RelatedActivityType codes
RELATED_PARENT = "1"
RELATED_CHILD = "2"
RELATED_SIBLING = "3"

ORG_TYPE_OTHER = "90"


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first(value: Any, default: Any = None) -> Any:
    items = as_list(value)
    return items[0] if items else default


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value).date()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Transaction:
    index: int
    type: str
    date: date | None
    value_date: date | None
    value: float
    currency: str | None
    ref: str | None
    provider_ref: str | None
    provider_name: str | None
    receiver_ref: str | None
    receiver_name: str | None
    receiver_type: str | None
    humanitarian: bool | None

    def locator(self) -> dict[str, Any]:
        return {
            "kind": "transaction",
            "index": self.index,
            "type": self.type,
            "date": self.date.isoformat() if self.date else None,
            "value": self.value,
            "currency": self.currency,
            "ref": self.ref,
        }


@dataclass(frozen=True)
class Budget:
    index: int
    type: str | None
    status: str | None
    period_start: date | None
    period_end: date | None
    value: float
    value_date: date | None
    currency: str | None

    def locator(self) -> dict[str, Any]:
        return {
            "kind": "budget",
            "index": self.index,
            "type": self.type,
            "status": self.status,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "value": self.value,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class Sector:
    vocabulary: str
    code: str
    percentage: float | None


@dataclass(frozen=True)
class RecipientCountry:
    code: str
    percentage: float | None


@dataclass(frozen=True)
class ParticipatingOrg:
    ref: str | None
    name: str | None
    role: str | None
    type: str | None


@dataclass(frozen=True)
class RelatedActivityRef:
    ref: str
    type: str


@dataclass
class Activity:
    identifier: str
    raw: dict[str, Any] = field(repr=False)
    title: str
    descriptions: list[str]
    status: str | None
    hierarchy: int | None
    currency: str | None
    dates: dict[str, date]
    last_updated: datetime | None
    reporting_org_ref: str | None
    reporting_org_names: list[str]
    sectors: list[Sector]
    recipient_countries: list[RecipientCountry]
    recipient_region_codes: list[str]
    participating_orgs: list[ParticipatingOrg]
    related: list[RelatedActivityRef]
    policy_markers: dict[str, str]
    default_flow_type: str | None
    default_aid_types: list[str]
    default_finance_type: str | None
    default_tied_status: str | None
    collaboration_type: str | None
    humanitarian: bool | None
    location_positions: list[str]
    transactions: list[Transaction] = field(default_factory=list)
    budgets: list[Budget] = field(default_factory=list)
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)

    @property
    def planned_start(self) -> date | None:
        return self.dates.get(PLANNED_START)

    @property
    def actual_start(self) -> date | None:
        return self.dates.get(ACTUAL_START)

    @property
    def planned_end(self) -> date | None:
        return self.dates.get(PLANNED_END)

    @property
    def actual_end(self) -> date | None:
        return self.dates.get(ACTUAL_END)

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    def sum_transactions(self, *types: str) -> float:
        return sum(t.value for t in self.transactions if t.type in types)

    def raw_list(self, key: str) -> list:
        return as_list(self.raw.get(key))


def _activity_from_doc(doc: dict[str, Any]) -> Activity:
    dates: dict[str, date] = {}
    for dtype, dvalue in zip(as_list(doc.get("activity_date_type")), as_list(doc.get("activity_date_iso_date"))):
        parsed = parse_date(dvalue)
        if parsed and dtype not in dates:
            dates[dtype] = parsed

    sectors = [
        Sector(vocabulary=v, code=c, percentage=p)
        for v, c, p in _zip_pad(
            as_list(doc.get("sector_vocabulary")),
            as_list(doc.get("sector_code")),
            as_list(doc.get("sector_percentage")),
        )
    ]
    countries = [
        RecipientCountry(code=c, percentage=p)
        for c, p in _zip_pad(
            as_list(doc.get("recipient_country_code")),
            as_list(doc.get("recipient_country_percentage")),
        )
    ]
    orgs = [
        ParticipatingOrg(ref=r, name=n, role=role, type=t)
        for r, n, role, t in _zip_pad(
            as_list(doc.get("participating_org_ref")),
            as_list(doc.get("participating_org_narrative")),
            as_list(doc.get("participating_org_role")),
            as_list(doc.get("participating_org_type")),
        )
    ]
    related = [
        RelatedActivityRef(ref=r, type=t)
        for r, t in zip(as_list(doc.get("related_activity_ref")), as_list(doc.get("related_activity_type")))
    ]
    markers = dict(
        zip(as_list(doc.get("policy_marker_code")), as_list(doc.get("policy_marker_significance")))
    )

    return Activity(
        identifier=doc["iati_identifier"],
        raw=doc,
        title=first(doc.get("title_narrative"), "") or "",
        descriptions=[d for d in as_list(doc.get("description_narrative")) if d],
        status=doc.get("activity_status_code"),
        hierarchy=doc.get("hierarchy"),
        currency=doc.get("default_currency"),
        dates=dates,
        last_updated=parse_datetime(doc.get("last_updated_datetime")),
        reporting_org_ref=doc.get("reporting_org_ref"),
        reporting_org_names=as_list(doc.get("reporting_org_narrative")),
        sectors=sectors,
        recipient_countries=countries,
        recipient_region_codes=as_list(doc.get("recipient_region_code")),
        participating_orgs=orgs,
        related=related,
        policy_markers=markers,
        default_flow_type=doc.get("default_flow_type_code"),
        default_aid_types=as_list(doc.get("default_aid_type_code")),
        default_finance_type=doc.get("default_finance_type_code"),
        default_tied_status=doc.get("default_tied_status_code"),
        collaboration_type=doc.get("collaboration_type_code"),
        humanitarian=doc.get("humanitarian"),
        location_positions=as_list(doc.get("location_point_pos")),
    )


def _zip_pad(*lists: list) -> list[tuple]:
    """Zip lists of possibly different lengths, padding the shorter ones with None.

    Solr drops empty attributes, so e.g. `participating_org_ref` can be shorter than
    `participating_org_narrative`. Padding keeps every element visible to rules; rules
    that care about the length mismatch check it explicitly.
    """
    n = max((len(lst) for lst in lists), default=0)
    return [tuple(lst[i] if i < len(lst) else None for lst in lists) for i in range(n)]


def _transaction_from_doc(doc: dict[str, Any], index: int) -> Transaction:
    return Transaction(
        index=index,
        type=first(doc.get("transaction_transaction_type_code"), "") or "",
        date=parse_date(first(doc.get("transaction_transaction_date_iso_date"))),
        value_date=parse_date(first(doc.get("transaction_value_value_date"))),
        value=float(first(doc.get("transaction_value"), 0.0) or 0.0),
        currency=first(doc.get("transaction_value_currency")) or doc.get("default_currency"),
        ref=first(doc.get("transaction_ref")),
        provider_ref=first(doc.get("transaction_provider_org_ref")),
        provider_name=first(doc.get("transaction_provider_org_narrative")),
        receiver_ref=first(doc.get("transaction_receiver_org_ref")),
        receiver_name=first(doc.get("transaction_receiver_org_narrative")),
        receiver_type=first(doc.get("transaction_receiver_org_type")),
        humanitarian=first(doc.get("transaction_humanitarian")),
    )


def _budget_from_doc(doc: dict[str, Any], index: int) -> Budget:
    return Budget(
        index=index,
        type=first(doc.get("budget_type")),
        status=first(doc.get("budget_status")),
        period_start=parse_date(first(doc.get("budget_period_start_iso_date"))),
        period_end=parse_date(first(doc.get("budget_period_end_iso_date"))),
        value=float(first(doc.get("budget_value"), 0.0) or 0.0),
        value_date=parse_date(first(doc.get("budget_value_value_date"))),
        currency=first(doc.get("budget_value_currency")) or doc.get("default_currency"),
    )


@dataclass
class Dataset:
    org_id: str
    activities: dict[str, Activity]
    today: date
    # identifier -> metadata of every document seen with that identifier (only when > 1)
    duplicate_identifiers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Org-wide statistics used by outlier-style rules
    transaction_value_p99: float | None = None
    _identifiers: set[str] | None = field(default=None, init=False, repr=False)

    @property
    def identifiers(self) -> set[str]:
        if self._identifiers is None:
            self._identifiers = set(self.activities)
        return self._identifiers

    def get(self, identifier: str) -> Activity | None:
        return self.activities.get(identifier)

    def __iter__(self):
        return iter(self.activities.values())

    def __len__(self) -> int:
        return len(self.activities)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.warning("%s not found; treating as empty", path)
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_dataset(org_dir: Path, org_id: str, today: date | None = None) -> Dataset:
    """Load `activity/transaction/budget.jsonl` from `org_dir` into a linked Dataset."""
    activities: dict[str, Activity] = {}
    seen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in _read_jsonl(org_dir / "activity.jsonl"):
        activity = _activity_from_doc(doc)
        seen[activity.identifier].append(
            {
                "title": activity.title,
                "status": activity.status,
                "last_updated": doc.get("last_updated_datetime"),
                "dataset_generated": doc.get("dataset_generated_datetime"),
            }
        )
        # Keep the most recently updated document when an identifier repeats.
        existing = activities.get(activity.identifier)
        if existing is None or (
            activity.last_updated
            and (existing.last_updated is None or activity.last_updated > existing.last_updated)
        ):
            activities[activity.identifier] = activity
    duplicates = {k: v for k, v in seen.items() if len(v) > 1}

    per_activity_txn: dict[str, list[Transaction]] = defaultdict(list)
    for doc in _read_jsonl(org_dir / "transaction.jsonl"):
        aid = doc.get("iati_identifier")
        per_activity_txn[aid].append(_transaction_from_doc(doc, len(per_activity_txn[aid])))
    per_activity_budget: dict[str, list[Budget]] = defaultdict(list)
    for doc in _read_jsonl(org_dir / "budget.jsonl"):
        aid = doc.get("iati_identifier")
        per_activity_budget[aid].append(_budget_from_doc(doc, len(per_activity_budget[aid])))

    for aid, activity in activities.items():
        activity.transactions = sorted(
            per_activity_txn.get(aid, []), key=lambda t: (t.date or date.min, t.index)
        )
        activity.budgets = sorted(
            per_activity_budget.get(aid, []), key=lambda b: (b.period_start or date.min, b.index)
        )

    # Resolve hierarchy links in both directions from the child's "parent" relation.
    for activity in activities.values():
        for rel in activity.related:
            if rel.type == RELATED_PARENT and activity.parent_id is None:
                activity.parent_id = rel.ref
                parent = activities.get(rel.ref)
                if parent is not None:
                    parent.child_ids.append(activity.identifier)

    values = [abs(t.value) for a in activities.values() for t in a.transactions if t.value]
    p99 = None
    if len(values) >= 100:
        p99 = statistics.quantiles(values, n=100)[98]

    return Dataset(
        org_id=org_id,
        activities=activities,
        today=today or datetime.now(UTC).date(),
        duplicate_identifiers=duplicates,
        transaction_value_p99=p99,
    )
