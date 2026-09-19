"""Section E: participating organisations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from iati_scout.quality.findings import Category, Issue
from iati_scout.quality.model import (
    ORG_TYPE_OTHER,
    ROLE_ACCOUNTABLE,
    ROLE_FUNDING,
    ROLE_IMPLEMENTING,
    Activity,
)
from iati_scout.quality.registry import Context, rule

ROLE_NAMES = {"1": "Funding", "2": "Accountable", "3": "Extending", "4": "Implementing"}


def _roles(a: Activity) -> set[str]:
    return {o.role for o in a.participating_orgs if o.role}


@rule("E-E01", Category.PARTICIPATING, "No funding or accountable organisation")
def missing_funding_or_accountable(a: Activity, ctx: Context) -> Iterator[Issue]:
    roles = _roles(a)
    for role in (ROLE_FUNDING, ROLE_ACCOUNTABLE):
        if role not in roles:
            yield Issue(
                f"No participating organisation with role {role} ({ROLE_NAMES[role]}); "
                f"roles present: {', '.join(sorted(roles)) or 'none'}",
                {"missing_role": role, "roles_present": sorted(roles)},
            )


@rule("W-E02", Category.PARTICIPATING, "No implementing organisation")
def missing_implementing(a: Activity, ctx: Context) -> Iterator[Issue]:
    roles = _roles(a)
    if ROLE_IMPLEMENTING not in roles:
        yield Issue(
            f"No participating organisation with role {ROLE_IMPLEMENTING} (Implementing); "
            f"roles present: {', '.join(sorted(roles)) or 'none'}",
            {"missing_role": ROLE_IMPLEMENTING, "roles_present": sorted(roles)},
        )


@rule("W-E03", Category.PARTICIPATING, "Organisation listed twice with the same role")
def duplicate_participating_org(a: Activity, ctx: Context) -> Iterator[Issue]:
    counts = Counter(
        ((o.name or o.ref or "").strip().lower(), o.role) for o in a.participating_orgs
    )
    for (name, role), n in counts.items():
        if n > 1 and name:
            yield Issue(
                f"'{name}' appears {n} times with role {role} ({ROLE_NAMES.get(role, role)})",
                {"organisation": name, "role": role, "count": n},
            )


@rule("W-E04", Category.PARTICIPATING, "Participating organisations without identifier")
def participating_org_without_ref(a: Activity, ctx: Context) -> Iterator[Issue]:
    refs = a.raw_list("participating_org_ref")
    names = a.raw_list("participating_org_narrative")
    if len(refs) < len(names):
        yield Issue(
            f"{len(names)} participating organisations but only {len(refs)} have an "
            f"organisation identifier (@ref): {', '.join(names)}",
            {"names": names, "refs": refs},
        )


@rule("W-E05", Category.PARTICIPATING, "Participating organisation type 'Other'")
def participating_org_type_other(a: Activity, ctx: Context) -> Iterator[Issue]:
    for o in a.participating_orgs:
        if o.type == ORG_TYPE_OTHER:
            yield Issue(
                f"Participating organisation '{o.name or o.ref}' (role {o.role}) is typed 90 "
                f"(Other); a specific organisation type is expected",
                {"organisation": o.name, "ref": o.ref, "role": o.role, "type": o.type},
            )
