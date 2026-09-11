"""Section C: sectors, countries/regions, policy markers and default classifications."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from iati_scout.quality.findings import Issue, Severity, fmt_pct
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


@rule("E-C01", Severity.ERROR, "DAC sector percentages do not sum to 100")
def dac_sector_percentages(a: Activity, ctx: Context) -> Iterator[Issue]:
    tol = ctx.t("percentage_tolerance")
    sums = _sector_sums(a)
    if DAC_SECTOR_VOCABULARY not in sums:
        return
    total, pcts, count = sums[DAC_SECTOR_VOCABULARY]
    if count > 1 and abs(total - 100) > tol:
        yield Issue(
            f"DAC sector percentages sum to {total:g}% across {count} sectors, expected 100%",
            {"vocabulary": DAC_SECTOR_VOCABULARY, "percentages": pcts, "sum": total},
        )


@rule("W-C02", Severity.WARNING, "Non-DAC sector percentages do not sum to 100")
def other_sector_percentages(a: Activity, ctx: Context) -> Iterator[Issue]:
    tol = ctx.t("percentage_tolerance")
    for vocab, (total, pcts, count) in _sector_sums(a).items():
        if vocab == DAC_SECTOR_VOCABULARY:
            continue
        if count > 1 and abs(total - 100) > tol:
            yield Issue(
                f"Sector vocabulary {vocab} percentages sum to {total:g}% across {count} codes, "
                f"expected 100%",
                {"vocabulary": vocab, "percentages": pcts, "sum": total},
            )


@rule("E-C03", Severity.ERROR, "Recipient-country percentages do not sum to 100")
def country_percentages(a: Activity, ctx: Context) -> Iterator[Issue]:
    if len(a.recipient_countries) < 2:
        return
    pcts = [c.percentage for c in a.recipient_countries]
    if any(p is None for p in pcts):
        yield Issue(
            f"{len(a.recipient_countries)} recipient countries but percentages are missing for "
            f"some of them",
            {"countries": [c.code for c in a.recipient_countries], "percentages": pcts},
        )
        return
    total = sum(pcts)
    if abs(total - 100) > ctx.t("percentage_tolerance"):
        yield Issue(
            f"Recipient-country percentages sum to {total:g}% across "
            f"{len(a.recipient_countries)} countries, expected 100%",
            {"countries": [c.code for c in a.recipient_countries], "percentages": pcts, "sum": total},
        )


@rule("E-C04", Severity.ERROR, "Recipient country and region both given without percentages")
def country_and_region(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.recipient_countries and a.recipient_region_codes:
        country_pcts = [c.percentage for c in a.recipient_countries]
        region_pcts = a.raw_list("recipient_region_percentage")
        if any(p is None for p in country_pcts) or len(region_pcts) < len(a.recipient_region_codes):
            yield Issue(
                f"Both recipient-country ({', '.join(c.code for c in a.recipient_countries)}) and "
                f"recipient-region ({', '.join(a.recipient_region_codes)}) are given, so each "
                f"needs a percentage",
                {
                    "countries": [c.code for c in a.recipient_countries],
                    "country_percentages": country_pcts,
                    "regions": a.recipient_region_codes,
                    "region_percentages": region_pcts,
                },
            )


@rule("E-C05", Severity.ERROR, "Sector or country with 0 percent")
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


@rule("W-C06", Severity.WARNING, "Gender-equality sector without gender marker")
def gender_sector_without_marker(a: Activity, ctx: Context) -> Iterator[Issue]:
    has_sector = any(s.code == SECTOR_GENDER_EQUALITY for s in a.sectors)
    marker = a.policy_markers.get(MARKER_GENDER)
    if has_sector and marker in (None, MARKER_NOT_TARGETED):
        yield Issue(
            f"Sector {SECTOR_GENDER_EQUALITY} (gender equality) is reported but the gender "
            f"policy marker is {marker or 'absent'}",
            {"sector": SECTOR_GENDER_EQUALITY, "gender_marker": marker},
        )


@rule("W-C07", Severity.WARNING, "Gender marker 'principal' without gender-equality sector")
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


@rule("W-C08", Severity.WARNING, "Home country as recipient country")
def home_country_recipient(a: Activity, ctx: Context) -> Iterator[Issue]:
    home = ctx.t("home_country")
    for c in a.recipient_countries:
        if c.code == home:
            yield Issue(
                f"Recipient country is {home} ({fmt_pct(c.percentage)}), the reporting "
                f"organisation's home country; check whether it is a genuine recipient",
                {"country": home, "percentage": c.percentage, "flow_type": a.default_flow_type},
            )


@rule("W-C09", Severity.WARNING, "Humanitarian flag absent")
def humanitarian_absent(a: Activity, ctx: Context) -> Iterator[Issue]:
    if a.humanitarian is None:
        yield Issue(
            "The humanitarian attribute is absent; publish an explicit true/false",
            {"humanitarian": None},
        )


@rule("W-C10", Severity.WARNING, "Missing default classification")
def missing_defaults(a: Activity, ctx: Context) -> Iterator[Issue]:
    missing = [label for attr, label in DEFAULT_FIELDS.items() if not getattr(a, attr)]
    if missing:
        yield Issue(
            f"Missing default classification(s): {', '.join(missing)}",
            {"missing": missing},
        )
