"""Finding payload, shaped to match the official IATI Validator report.

`iati-scout` no longer re-implements the IATI standard ruleset — those checks
come from the official validator (see `iati_scout.validator`). What stays here
are the *additional* checks IATI does not make, and they are emitted in the
same shape as the validator's own findings so a consumer only has to
understand one format:

    {id, severity, message, category, context: [{text, ...}], details}

Two deliberate deviations from the contract, both additive:

- `severity` for every scout rule is ``advisory`` — the validator's own scale
  reserves error/warning for violations of the published standard, and a scout
  rule is a heuristic, not a standard violation.
- Because the validator *also* emits ``advisory`` (its 1000.x linked-activity
  checks), severity alone cannot tell the two apart. Every finding therefore
  carries `source`: ``"validator"`` or ``"scout"``.

The scout-only extras (`evidence`, `item`, `related`, `urls`, `systemic`) live
under `details`, which the contract already defines as a free-form object.
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
    """The IATI Validator's four-level scale, most severe first."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    ADVISORY = "advisory"


SEVERITY_ORDER = [
    Severity.CRITICAL,
    Severity.ERROR,
    Severity.WARNING,
    Severity.ADVISORY,
]


class Category(str, Enum):
    """The official category vocabulary, taken from the IATI ruleset's `ruleInfo.category`."""

    IATI = "iati"
    IDENTIFIERS = "identifiers"
    INFORMATION = "information"
    CLASSIFICATIONS = "classifications"
    FINANCIAL = "financial"
    RELATIONS = "relations"
    GEO = "geo"
    ORGANISATION = "organisation"
    PARTICIPATING = "participating"
    PERFORMANCE = "performance"


class Source(str, Enum):
    VALIDATOR = "validator"
    SCOUT = "scout"


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

    The runner combines it with the rule's code/category/title and the
    activity's identity and links to produce a full `Finding`.
    """

    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    item: dict[str, Any] | None = None
    related: list[RelatedActivity] = field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    """One finding, from either source, in the validator's vocabulary.

    `code` is the validator's `id`: a dotted number for an official rule
    (``7.5.3``), a scout rule code for our own (``W-B12``). The two namespaces
    cannot collide, so the shared field is unambiguous.
    """

    code: str
    severity: Severity
    category: Category
    source: Source
    rule_title: str
    iati_identifier: str
    activity_title: str
    message: str
    context: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    item: dict[str, Any] | None = None
    related: list[RelatedActivity] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    systemic: bool = False

    def to_dict(self) -> dict[str, Any]:
        """The flat form used by findings.jsonl/csv and the dashboard export."""
        data = asdict(self)
        data["severity"] = self.severity.value
        data["category"] = self.category.value
        data["source"] = self.source.value
        data["evidence"] = {k: _jsonable(v) for k, v in self.evidence.items()}
        return data

    def to_validator_error(self) -> dict[str, Any]:
        """The nested form the official report uses inside `report.errors[].errors[].errors[]`."""
        details: dict[str, Any] = {}
        if self.source == Source.SCOUT:
            details = {
                "source": self.source.value,
                "rule_title": self.rule_title,
                "systemic": self.systemic,
                "evidence": {k: _jsonable(v) for k, v in self.evidence.items()},
                "urls": self.urls,
            }
            if self.item:
                details["item"] = _jsonable(self.item)
            if self.related:
                details["related"] = [asdict(r) for r in self.related]
        error: dict[str, Any] = {
            "id": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "context": self.context,
        }
        if details:
            error["details"] = details
        return error


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
