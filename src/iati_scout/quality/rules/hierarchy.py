"""Section D: hierarchy and related-activity consistency."""

from __future__ import annotations

from collections.abc import Iterator

from iati_scout.quality.findings import Issue, RelatedActivity, Severity, fmt_date
from iati_scout.quality.model import (
    RELATED_PARENT,
    STATUS_IMPLEMENTATION,
    Activity,
)
from iati_scout.quality.registry import Context, rule

RELATION_NAMES = {"1": "parent", "2": "child", "3": "sibling", "4": "co-funded", "5": "third-party"}


def _parent_of(a: Activity, ctx: Context) -> Activity | None:
    return ctx.dataset.get(a.parent_id) if a.parent_id else None


def _related_parent(p: Activity) -> RelatedActivity:
    return RelatedActivity.build(p.identifier, "parent", p.title)


@rule("E-D01", Severity.ERROR, "Related activity not found in the organisation's data")
def related_not_found(a: Activity, ctx: Context) -> Iterator[Issue]:
    for rel in a.related:
        if rel.ref not in ctx.dataset.identifiers:
            yield Issue(
                f"Related activity {rel.ref} ({RELATION_NAMES.get(rel.type, rel.type)}) does not "
                f"exist in the organisation's published activities",
                {"related_ref": rel.ref, "relation_type": rel.type},
                related=[RelatedActivity.build(rel.ref, RELATION_NAMES.get(rel.type, rel.type))],
            )


@rule("E-D02", Severity.ERROR, "Activity related to itself")
def related_to_self(a: Activity, ctx: Context) -> Iterator[Issue]:
    for rel in a.related:
        if rel.ref == a.identifier:
            yield Issue(
                f"Activity lists itself as a related activity "
                f"({RELATION_NAMES.get(rel.type, rel.type)})",
                {"related_ref": rel.ref, "relation_type": rel.type},
            )


@rule("E-D03", Severity.ERROR, "Hierarchy level without matching relations")
def hierarchy_without_relations(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.hierarchy == 2 and not any(r.type == RELATED_PARENT for r in a.related):
        yield Issue(
            "Hierarchy is 2 but no parent (related-activity type 1) is declared",
            {"hierarchy": a.hierarchy, "related": [(r.ref, r.type) for r in a.related]},
        )
    if a.hierarchy == 1 and not a.child_ids:
        yield Issue(
            "Hierarchy is 1 but no published activity declares it as parent",
            {"hierarchy": a.hierarchy, "child_count": 0},
        )


@rule("E-D04", Severity.ERROR, "Child actual dates outside parent actual dates")
def child_actual_dates_outside_parent(a: Activity, ctx: Context) -> Iterator[Issue]:
    p = _parent_of(a, ctx)
    if p is None:
        return
    if a.actual_start and p.actual_start and a.actual_start < p.actual_start:
        yield Issue(
            f"Actual start {fmt_date(a.actual_start)} is before parent {p.identifier}'s actual "
            f"start {fmt_date(p.actual_start)}",
            {"child_actual_start": a.actual_start, "parent_actual_start": p.actual_start},
            related=[_related_parent(p)],
        )
    if a.actual_end and p.actual_end and a.actual_end > p.actual_end:
        yield Issue(
            f"Actual end {fmt_date(a.actual_end)} is after parent {p.identifier}'s actual end "
            f"{fmt_date(p.actual_end)}",
            {"child_actual_end": a.actual_end, "parent_actual_end": p.actual_end},
            related=[_related_parent(p)],
        )


@rule("E-D05", Severity.ERROR, "Activity identifier published more than once")
def duplicate_identifier(a: Activity, ctx: Context) -> Iterator[Issue]:
    docs = ctx.dataset.duplicate_identifiers.get(a.identifier)
    if docs:
        generated = sorted({d.get("dataset_generated") or "?" for d in docs})
        yield Issue(
            f"Identifier appears {len(docs)} times in the Datastore (source files generated "
            f"{', '.join(generated)}); an IATI identifier must be unique",
            {"occurrences": docs},
        )


@rule("W-D05", Severity.WARNING, "Child planned end after parent planned end")
def child_planned_end_after_parent(a: Activity, ctx: Context) -> Iterator[Issue]:
    p = _parent_of(a, ctx)
    if p and a.planned_end and p.planned_end and a.planned_end > p.planned_end:
        yield Issue(
            f"Planned end {fmt_date(a.planned_end)} is after parent {p.identifier}'s planned end "
            f"{fmt_date(p.planned_end)}",
            {"child_planned_end": a.planned_end, "parent_planned_end": p.planned_end},
            related=[_related_parent(p)],
        )


@rule("W-D06", Severity.WARNING, "Child recipient country not in parent's countries")
def child_country_not_in_parent(a: Activity, ctx: Context) -> Iterator[Issue]:
    p = _parent_of(a, ctx)
    if p is None or not p.recipient_countries:
        return
    parent_codes = {c.code for c in p.recipient_countries}
    extra = [c.code for c in a.recipient_countries if c.code not in parent_codes]
    if extra:
        yield Issue(
            f"Recipient country {', '.join(extra)} is not among parent {p.identifier}'s "
            f"countries ({', '.join(sorted(parent_codes))})",
            {"child_countries_not_in_parent": extra, "parent_countries": sorted(parent_codes)},
            related=[_related_parent(p)],
        )


@rule("W-D07", Severity.WARNING, "Child default classification differs from parent")
def child_defaults_differ(a: Activity, ctx: Context) -> Iterator[Issue]:
    p = _parent_of(a, ctx)
    if p is None:
        return
    checks = (
        ("default-flow-type", a.default_flow_type, p.default_flow_type),
        ("default-aid-type", a.default_aid_types, p.default_aid_types),
        ("default-finance-type", a.default_finance_type, p.default_finance_type),
    )
    for label, child_value, parent_value in checks:
        if child_value and parent_value and child_value != parent_value:
            yield Issue(
                f"{label} {child_value} differs from parent {p.identifier}'s {parent_value}",
                {"field": label, "child": child_value, "parent": parent_value},
                related=[_related_parent(p)],
            )


@rule("W-D08", Severity.WARNING, "Parent closed while child still in implementation")
def parent_closed_child_implementing(a: Activity, ctx: Context) -> Iterator[Issue]:
    p = _parent_of(a, ctx)
    if p and p.is_closed and a.status == STATUS_IMPLEMENTATION:
        yield Issue(
            f"Status is Implementation (2) but parent {p.identifier} has status {p.status} "
            f"(finalisation/closed)",
            {"child_status": a.status, "parent_status": p.status},
            related=[_related_parent(p)],
        )
