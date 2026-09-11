"""Write fetched Datastore documents to disk as JSONL, plus a run manifest."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from iati_scout import __version__

logger = logging.getLogger(__name__)


def write_jsonl(docs: Iterable[dict], path: Path) -> int:
    """Write `docs` to `path` as JSON Lines, atomically. Returns the count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False))
            f.write("\n")
            count += 1
    tmp_path.replace(path)
    return count


def _log_progress(docs: Iterator[dict], collection: str, every: int = 500) -> Iterator[dict]:
    for i, doc in enumerate(docs, start=1):
        yield doc
        if i % every == 0:
            logger.info("  %s: %d docs written so far", collection, i)


def fetch_organisation(client, org_id: str, collections: tuple[str, ...], data_dir: Path) -> dict:
    """Fetch all `collections` for `org_id` via `client`, writing JSONL + manifest.

    Returns the manifest dict that was written.
    """
    org_dir = data_dir / org_id
    manifest = {
        "org_id": org_id,
        "fetched_at": datetime.now(UTC).isoformat(),
        "tool_version": __version__,
        "collections": {},
    }

    for collection in collections:
        logger.info("Fetching %s for %s ...", collection, org_id)
        stats: dict = {}
        docs = client.iter_docs(collection, org_id, stats=stats)
        out_path = org_dir / f"{collection}.jsonl"
        written = write_jsonl(_log_progress(docs, collection), out_path)
        num_found = stats.get("num_found", written)
        manifest["collections"][collection] = {
            "num_found": num_found,
            "written": written,
            "file": f"{org_id}/{collection}.jsonl",
        }
        if written != num_found:
            logger.warning(
                "%s: wrote %d docs but Datastore reported numFound=%d",
                collection,
                written,
                num_found,
            )
        else:
            logger.info("%s: wrote %d docs", collection, written)

    manifest_path = org_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp_path.replace(manifest_path)

    return manifest
