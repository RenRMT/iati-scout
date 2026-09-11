"""Finding payload: self-contained description of one detected issue.

Designed so a later dashboard/UI can render a finding without re-opening the raw
data: the message quotes the offending values, `evidence` lists them
structurally, `item` locates the row (transaction/budget) when relevant,
`related` names other activities involved, and `urls` link out to d-portal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any
from urllib.parse import quote

D_PORTAL_ACTIVITY_URL = "https://d-portal.iatistandard.org/ctrack.html#view=act&aid={identifier}"
DATASTORE_ACTIVITY_URL = (
    "https://api.iatistandard.org/datastore/activity/select?q=iati_identifier:%22{identifier}%22"
)


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


def d_portal_activity_url(identifier: str) -> str:
    # Identifier lives in a URL fragment; keep it readable but neutralise
    # characters that would break the fragment or query parsing.
    return D_PORTAL_ACTIVITY_URL.format(identifier=quote(identifier, safe="-_.:"))


def datastore_activity_url(identifier: str) -> str:
    return DATASTORE_ACTIVITY_URL.format(identifier=quote(identifier, safe="-_.:"))


@dataclass(frozen=True)
class RelatedActivity:
    identifier: str
    relation: str  # "parent", "child", "related", ...
    title: str | None = None
    url: str | None = None

    @classmethod
    def build(cls, identifier: str, relation: str, title: str | None = None) -> RelatedActivity:
        return cls(
            identifier=identifier,
            relation=relation,
            title=title,
            url=d_portal_activity_url(identifier),
        )


@dataclass(frozen=True)
class Issue:
    """What a rule yields: the rule-specific part of a finding.

    The runner combines it with the rule's code/severity/title and the activity's
    identity and links to produce a full `Finding`.
    """

    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    item: dict[str, Any] | None = None
    related: list[RelatedActivity] = field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    rule_title: str
    iati_identifier: str
    activity_title: str
    message: str
    evidence: dict[str, Any]
    item: dict[str, Any] | None
    related: list[RelatedActivity]
    urls: dict[str, str]
    systemic: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["evidence"] = {k: _jsonable(v) for k, v in self.evidence.items()}
        return data


def _jsonable(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


# --- formatting helpers used by rules to build readable messages -----------


def fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "(none)"


def fmt_money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "(none)"
    amount = f"{value:,.2f}".replace(",", " ")
    return f"{currency or ''} {amount}".strip()


def fmt_pct(value: float | None) -> str:
    return "(none)" if value is None else f"{value:g}%"
