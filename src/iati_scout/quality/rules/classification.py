"""Section C: sectors, countries/regions, policy markers and default classifications."""

from __future__ import annotations

from collections import defaultdict
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


def _sector_sums(a: Activity) -> dict[str, tuple[float, list[float | None], int]]:
    """vocabulary -> (sum of percentages, percentages, number of sectors)."""
    per_vocab: dict[str, list[float | None]] = defaultdict(list)
    for s in a.sectors:
        per_vocab[s.vocabulary or DAC_SECTOR_VOCABULARY].append(s.percentage)
    return {
        v: (sum(p for p in pcts if p is not None), pcts, len(pcts)) for v, pcts in per_vocab.items()
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


def dac_sector_percentage_completeness(a: Activity, ctx: Context) -> Iterator[Issue]:
    tol = ctx.t("percentage_tolerance")
    sums = _sector_sums(a)
    if DAC_SECTOR_VOCABULARY not in sums:
        return
    _total, pcts, count = sums[DAC_SECTOR_VOCABULARY]
    codes = [s.code for s in a.sectors if (s.vocabulary or DAC_SECTOR_VOCABULARY) == DAC_SECTOR_VOCABULARY]
    if count > 1 and any(p is None for p in pcts):
        yield Issue(
            f"{count} DAC sectors declared ({', '.join(codes)}) but a percentage is "
            f"missing for at least one of them",
            {"sectors": codes, "percentages": pcts},
        )
    elif count == 1 and pcts[0] is not None and abs(pcts[0] - 100) > tol:
        yield Issue(
            f"Single DAC sector {codes[0]} has percentage {pcts[0]:g}%, which should "
            f"be omitted or set to 100",
            {"sector": codes[0], "percentage": pcts[0]},
        )


def single_country_percentage(a: Activity, ctx: Context) -> Iterator[Issue]:
    tol = ctx.t("percentage_tolerance")
    if len(a.recipient_countries) == 1:
        c = a.recipient_countries[0]
        if c.percentage is not None and abs(c.percentage - 100) > tol:
            yield Issue(
                f"Single recipient country {c.code} has percentage {c.percentage:g}%, "
                f"which should be omitted or set to 100",
                {"country": c.code, "percentage": c.percentage},
            )


def region_percentage_completeness(a: Activity, ctx: Context) -> Iterator[Issue]:
    tol = ctx.t("percentage_tolerance")
    regions = a.recipient_regions
    codes = [r.code for r in regions]
    pcts = [r.percentage for r in regions]
    if len(regions) > 1 and any(p is None for p in pcts):
        yield Issue(
            f"{len(regions)} recipient regions declared ({', '.join(codes)}) but a "
            f"percentage is missing for at least one of them",
            {"regions": codes, "percentages": pcts},
        )
    elif len(regions) == 1 and pcts[0] is not None and abs(pcts[0] - 100) > tol:
        yield Issue(
            f"Single recipient region {codes[0]} has percentage {pcts[0]:g}%, which "
            f"should be omitted or set to 100",
            {"region": codes[0], "percentage": pcts[0]},
        )


def region_percentages_sum(a: Activity, ctx: Context) -> Iterator[Issue]:
    tol = ctx.t("percentage_tolerance")
    regions = a.recipient_regions
    pcts = [r.percentage for r in regions]
    if len(regions) > 1 and all(p is not None for p in pcts):
        total = sum(pcts)
        if abs(total - 100) > tol:
            yield Issue(
                f"Recipient-region percentages sum to {total:g}% across {len(regions)} "
                f"regions, expected 100%",
                {"regions": [r.code for r in regions], "percentages": pcts, "sum": total},
            )


def default_language_missing(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.default_language:
        return
    title_langs = a.raw_list("title_narrative_xml_lang")
    description_langs = a.raw_list("description_narrative_xml_lang")
    if len(title_langs) < len(a.raw_list("title_narrative")) or any(not lang for lang in title_langs):
        yield Issue(
            "No default language (@xml:lang on iati-activity) and the title narrative "
            "does not specify a language",
            {"default_language": None, "title_narrative_xml_lang": title_langs},
        )
    if len(description_langs) < len(a.descriptions) or any(not lang for lang in description_langs):
        yield Issue(
            "No default language (@xml:lang on iati-activity) and at least one "
            "description narrative does not specify a language",
            {"default_language": None, "description_narrative_xml_lang": description_langs},
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
