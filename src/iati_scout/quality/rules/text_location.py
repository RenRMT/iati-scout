"""Section F: narrative text quality and location coordinates."""

from __future__ import annotations

from collections.abc import Iterator

from iati_scout.quality.findings import Category, Issue
from iati_scout.quality.model import Activity
from iati_scout.quality.registry import Context, rule


def _parse_pos(pos: str) -> tuple[float, float] | None:
    parts = pos.split()
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


@rule("E-F01", Category.GEO, "Location coordinates not parseable")
def location_pos_malformed(a: Activity, ctx: Context) -> Iterator[Issue]:
    for pos in a.location_positions:
        if _parse_pos(pos) is None:
            yield Issue(
                f"location/point/pos '{pos}' is not a valid 'latitude longitude' pair",
                {"pos": pos},
            )


@rule("E-F02", Category.GEO, "Location coordinates out of range or (0, 0)")
def location_pos_out_of_range(a: Activity, ctx: Context) -> Iterator[Issue]:
    for pos in a.location_positions:
        parsed = _parse_pos(pos)
        if parsed is None:
            continue
        lat, lon = parsed
        if lat == 0 and lon == 0:
            yield Issue("location/point/pos is (0, 0), the null island placeholder", {"pos": pos})
        elif abs(lat) > 90 or abs(lon) > 180:
            yield Issue(
                f"location/point/pos '{pos}' is outside the valid latitude/longitude range",
                {"pos": pos, "lat": lat, "lon": lon},
            )


@rule("W-F03", Category.GEO, "Location in home country while recipient country differs")
def location_in_home_country(a: Activity, ctx: Context) -> Iterator[Issue]:
    home = ctx.t("home_country")
    if any(c.code == home for c in a.recipient_countries):
        return
    lat_min, lon_min, lat_max, lon_max = ctx.t("home_bbox")
    for pos in a.location_positions:
        parsed = _parse_pos(pos)
        if parsed is None:
            continue
        lat, lon = parsed
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            yield Issue(
                f"Location {pos} lies in {home} while recipient country is "
                f"{', '.join(c.code for c in a.recipient_countries) or '(none)'}; "
                f"possibly the reporting organisation's own address",
                {"pos": pos, "recipient_countries": [c.code for c in a.recipient_countries]},
            )


@rule("W-F04", Category.INFORMATION, "Title quality")
def title_quality(a: Activity, ctx: Context) -> Iterator[Issue]:
    title = a.title
    if len(title.strip()) < ctx.t("title_min_length"):
        yield Issue(
            f"Title '{title}' is only {len(title.strip())} characters",
            {"title": title, "length": len(title.strip())},
        )
    if title.strip() and title.isupper() and len(title.strip()) > 3:
        yield Issue(f"Title '{title}' is all upper case", {"title": title})
    if title != title.strip() or "  " in title:
        yield Issue(
            f"Title '{title}' has leading/trailing or doubled whitespace",
            {"title": title},
        )


@rule("W-F05", Category.INFORMATION, "Description quality")
def description_quality(a: Activity, ctx: Context) -> Iterator[Issue]:
    min_len = ctx.t("description_min_length")
    trunc_lengths = set(ctx.t("truncation_lengths"))
    title_norm = a.title.strip().lower()
    for i, desc in enumerate(a.descriptions):
        text = desc.strip()
        if len(text) < min_len:
            yield Issue(
                f"Description #{i + 1} '{text}' is only {len(text)} characters",
                {"description": text, "length": len(text)},
            )
        if text.lower() == title_norm and title_norm:
            yield Issue(
                f"Description #{i + 1} is identical to the title '{a.title}'",
                {"description": text, "title": a.title},
            )
        if text.endswith(("...", "…")) or len(desc) in trunc_lengths:
            yield Issue(
                f"Description #{i + 1} looks truncated (length {len(desc)}, ends with "
                f"'{text[-20:]}')",
                {"length": len(desc), "ending": text[-40:]},
            )
