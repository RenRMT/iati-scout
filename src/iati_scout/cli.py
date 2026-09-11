"""Command-line entry point: `python -m iati_scout fetch [options]`."""

from __future__ import annotations

import argparse
import logging
import sys

from iati_scout.config import ConfigError, load_settings
from iati_scout.datastore import DatastoreClient, DatastoreError
from iati_scout.storage import fetch_organisation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iati-scout")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch all Datastore data for an organisation"
    )
    fetch_parser.add_argument(
        "--org-id", help="IATI organisation identifier, e.g. NL-KVK-27378529"
    )
    fetch_parser.add_argument(
        "--collections",
        help="Comma-separated list of collections to fetch (default: from config.toml)",
    )
    fetch_parser.add_argument(
        "--data-dir", help="Output directory for fetched data (default: from config.toml)"
    )
    fetch_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "fetch":
        return _fetch(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _fetch(args: argparse.Namespace) -> int:
    collections = args.collections.split(",") if args.collections else None
    try:
        settings = load_settings(
            org_id=args.org_id,
            collections=collections,
            data_dir=args.data_dir,
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    client = DatastoreClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        rows_per_page=settings.rows_per_page,
        min_request_interval=settings.min_request_interval,
    )

    try:
        manifest = fetch_organisation(
            client, settings.org_id, settings.collections, settings.data_dir
        )
    except DatastoreError as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 1

    mismatches = [
        name
        for name, info in manifest["collections"].items()
        if info["written"] != info["num_found"]
    ]
    if mismatches:
        print(
            f"Warning: written count did not match numFound for: {', '.join(mismatches)}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
