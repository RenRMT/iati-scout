"""Section H: identifier hygiene, matching checks from the IATI standard ruleset.

https://iatistandard.org/en/iati-standard/203/rulesets/standard-ruleset/ defines a set
of identifier-format rules (uniqueness, prefixing, whitespace, forbidden symbols).
Published data has almost always already passed these via the IATI Validator, so hits
here are rare — but a rare hit is a real, actionable problem, and re-checking costs
little. Coverage is intentionally partial: fields that require data this tool does not
model (the `iati-organisations` registration file, `other-identifier`/`owner-org`,
transaction-level `provider-activity-id`/`receiver-activity-id`) are left out; see
docs/patterns-learned.md or the project README for the full comparison against the
standard ruleset.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from iati_scout.quality.findings import Issue, Severity
from iati_scout.quality.model import Activity
from iati_scout.quality.registry import Context, rule

FORBIDDEN_SYMBOLS = re.compile(r"[/&|?]")


def _identifier_fields(a: Activity) -> Iterator[tuple[str, str]]:
    """(field label, value) for every identifier-bearing field this tool models."""
    yield "iati-identifier", a.identifier
    if a.reporting_org_ref:
        yield "reporting-org/@ref", a.reporting_org_ref
    for rel in a.related:
        if rel.ref:
            yield "related-activity/@ref", rel.ref
    for o in a.participating_orgs:
        if o.ref:
            yield "participating-org/@ref", o.ref
    for activity_id in a.raw_list("participating_org_activity_id"):
        if activity_id:
            yield "participating-org/@activity-id", activity_id


@rule(
    "E-H01",
    Severity.ERROR,
    "Activity identifier equals reporting-org identifier",
    "IATI ruleset 1.1.3: the activity identifier must differ from the organisation "
    "identifier of the reporting organisation.",
)
def activity_id_equals_reporting_org(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.reporting_org_ref and a.identifier == a.reporting_org_ref:
        yield Issue(
            f"Activity identifier '{a.identifier}' is identical to the reporting "
            f"organisation identifier",
            {"iati_identifier": a.identifier, "reporting_org_ref": a.reporting_org_ref},
        )


@rule(
    "W-H02",
    Severity.WARNING,
    "Activity identifier does not start with the reporting-org identifier",
    "IATI ruleset 1.1.21: the activity identifier should begin with the reporting "
    "organisation's identifier followed by a hyphen and a unique string.",
)
def activity_id_prefix(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.reporting_org_ref and not a.identifier.startswith(f"{a.reporting_org_ref}-"):
        yield Issue(
            f"Activity identifier '{a.identifier}' does not start with "
            f"'{a.reporting_org_ref}-'",
            {"iati_identifier": a.identifier, "reporting_org_ref": a.reporting_org_ref},
        )


@rule(
    "W-H03",
    Severity.WARNING,
    "Identifier has leading/trailing whitespace",
    "IATI ruleset 1.3.1/1.14.1/1.7.1/1.8.1/1.9.1 (consolidated): identifier fields "
    "should not start or end with spaces or newlines.",
)
def identifier_has_whitespace(a: Activity, ctx: Context) -> Iterator[Issue]:
    for label, value in _identifier_fields(a):
        if value != value.strip():
            yield Issue(
                f"{label} '{value}' has leading or trailing whitespace",
                {"field": label, "value": value},
            )


@rule(
    "W-H04",
    Severity.WARNING,
    "Identifier contains a forbidden symbol",
    "IATI ruleset 1.3.13/1.14.13/1.8.13 (consolidated): identifier fields must not "
    "contain the symbols /, &, | or ?.",
)
def identifier_has_forbidden_symbol(a: Activity, ctx: Context) -> Iterator[Issue]:
    for label, value in _identifier_fields(a):
        if FORBIDDEN_SYMBOLS.search(value):
            yield Issue(
                f"{label} '{value}' contains one of the forbidden symbols / & | ?",
                {"field": label, "value": value},
            )
