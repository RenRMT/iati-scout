"""Section C: sectors, countries/regions, policy markers and default classifications."""

from __future__ import annotations

from collections.abc import Iterator

from iati_scout.quality.findings import Category, Issue, fmt_pct
from iati_scout.quality.model import Activity
from iati_scout.quality.registry import Context, rule

DAC_SECTOR_VOCABULARY = "1"
SECTOR_GENDER_EQUALITY = "15170"
MARKER_GENDER = "1"
MARKER_PRINCIPAL = "2"
MARKER_NOT_TARGETED = "0"
FLOW_ODA = "10"

DEFAULT_FIELDS = {
    "default_flow_type": "default-flow-type",
    "default_aid_types": "default-aid-type",
    "default_finance_type": "default-finance-type",
    "default_tied_status": "default-tied-status",
    "collaboration_type": "collaboration-type",
}


@rule("E-C04", Category.CLASSIFICATIONS, "Recipient country and region both given without percentages")
def country_and_region(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.recipient_countries and a.recipient_regions:
        country_pcts = [c.percentage for c in a.recipient_countries]
        region_pcts = [r.percentage for r in a.recipient_regions]
        if any(p is None for p in country_pcts) or any(p is None for p in region_pcts):
            yield Issue(
                f"Both recipient-country ({', '.join(c.code for c in a.recipient_countries)}) and "
                f"recipient-region ({', '.join(r.code for r in a.recipient_regions)}) are given, so "
                f"each needs a percentage",
                {
                    "countries": [c.code for c in a.recipient_countries],
                    "country_percentages": country_pcts,
                    "regions": [r.code for r in a.recipient_regions],
                    "region_percentages": region_pcts,
                },
            )


@rule("E-C05", Category.CLASSIFICATIONS, "Sector or country with 0 percent")
def zero_percentage(a: Activity, ctx: Context) -> Iterator[Issue]:
    for s in a.sectors:
        if s.percentage == 0:
            yield Issue(
                f"Sector {s.code} (vocabulary {s.vocabulary}) has percentage 0%",
                {"sector": s.code, "vocabulary": s.vocabulary, "percentage": 0},
            )
    for c in a.recipient_countries:
        if c.percentage == 0:
            yield Issue(
                f"Recipient country {c.code} has percentage 0%",
                {"country": c.code, "percentage": 0},
            )


@rule("W-C06", Category.CLASSIFICATIONS, "Gender-equality sector without gender marker")
def gender_sector_without_marker(a: Activity, ctx: Context) -> Iterator[Issue]:
    has_sector = any(s.code == SECTOR_GENDER_EQUALITY for s in a.sectors)
    marker = a.policy_markers.get(MARKER_GENDER)
    if has_sector and marker in (None, MARKER_NOT_TARGETED):
        yield Issue(
            f"Sector {SECTOR_GENDER_EQUALITY} (gender equality) is reported but the gender "
            f"policy marker is {marker or 'absent'}",
            {"sector": SECTOR_GENDER_EQUALITY, "gender_marker": marker},
        )


@rule("W-C07", Category.CLASSIFICATIONS, "Gender marker 'principal' without gender-equality sector")
def gender_principal_without_sector(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.policy_markers.get(MARKER_GENDER) == MARKER_PRINCIPAL and not any(
        s.code == SECTOR_GENDER_EQUALITY for s in a.sectors
    ):
        yield Issue(
            f"Gender policy marker is 2 (principal objective) but sector "
            f"{SECTOR_GENDER_EQUALITY} is not among the sectors "
            f"({', '.join(s.code for s in a.sectors if s.vocabulary == DAC_SECTOR_VOCABULARY)})",
            {
                "gender_marker": MARKER_PRINCIPAL,
                "dac_sectors": [s.code for s in a.sectors if s.vocabulary == DAC_SECTOR_VOCABULARY],
            },
        )


@rule("W-C08", Category.CLASSIFICATIONS, "Home country as recipient country")
def home_country_recipient(a: Activity, ctx: Context) -> Iterator[Issue]:
    home = ctx.t("home_country")
    for c in a.recipient_countries:
        if c.code == home:
            yield Issue(
                f"Recipient country is {home} ({fmt_pct(c.percentage)}), the reporting "
                f"organisation's home country; check whether it is a genuine recipient",
                {"country": home, "percentage": c.percentage, "flow_type": a.default_flow_type},
            )


@rule("W-C09", Category.CLASSIFICATIONS, "Humanitarian flag absent")
def humanitarian_absent(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.humanitarian is None:
        yield Issue(
            "The humanitarian attribute is absent; publish an explicit true/false",
            {"humanitarian": None},
        )


@rule("W-C10", Category.CLASSIFICATIONS, "Missing default classification")
def missing_defaults(a: Activity, ctx: Context) -> Iterator[Issue]:
    missing = [label for attr, label in DEFAULT_FIELDS.items() if not getattr(a, attr)]
    if missing:
        yield Issue(
            f"Missing default classification(s): {', '.join(missing)}",
            {"missing": missing},
        )


# IATI ruleset 6.2.2/6.6.2/6.7.2 and 3.6.2/3.7.1/3.7.2 (sector and recipient
# country/region must be declared consistently at activity level OR for every
# transaction) are NOT implemented: the Datastore's transaction/select schema
# denormalizes the activity's own sector/recipient-country/recipient-region onto
# every transaction row regardless of whether the source XML has a genuine
# per-transaction override, so `sector_code`/`recipient_country_code` is present
# on effectively every transaction and this check cannot be built reliably from
# Datastore data alone (verified empirically: 46 732/46 732 RVO transaction rows
# carry a non-empty, activity-identical sector_code). It would need the raw
# `/iati` XML per activity.
