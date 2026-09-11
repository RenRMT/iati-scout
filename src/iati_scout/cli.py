"""Command-line entry point: `python -m iati_scout fetch [options]`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

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

    check_parser = subparsers.add_parser(
        "check", help="Run data-quality rules over previously fetched data"
    )
    check_parser.add_argument(
        "--org-id", help="IATI organisation identifier, e.g. NL-KVK-27378529"
    )
    check_parser.add_argument(
        "--data-dir", help="Directory holding data/raw/<org_id> (default: from config.toml)"
    )
    check_parser.add_argument(
        "--out-dir", help="Where to write reports (default: <data-dir>/../quality/<org_id>)"
    )
    check_parser.add_argument(
        "--rules", help="Comma-separated rule codes to run (default: all enabled in rules.toml)"
    )
    check_parser.add_argument(
        "--severity", choices=["error", "warning"], help="Only run rules of this severity"
    )
    check_parser.add_argument(
        "--list-rules", action="store_true", help="Print the rule catalogue and exit"
    )
    check_parser.add_argument(
        "--no-export",
        action="store_true",
        help="Skip writing the dashboard export (out-dir/export/)",
    )
    check_parser.add_argument(
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
    if args.command == "check":
        return _check(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _check(args: argparse.Namespace) -> int:
    import json

    from iati_scout.quality.export import write_export
    from iati_scout.quality.findings import Severity
    from iati_scout.quality.model import load_dataset
    from iati_scout.quality.registry import all_rules, load_rule_config
    from iati_scout.quality.report import write_reports
    from iati_scout.quality.runner import run_checks, select_rules

    if args.list_rules:
        for spec in all_rules():
            print(f"{spec.code}  {spec.severity.value:7s}  {spec.title}")
        return 0

    try:
        settings = load_settings(org_id=args.org_id, data_dir=args.data_dir, require_api_key=False)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    org_dir = settings.data_dir / settings.org_id
    if not (org_dir / "activity.jsonl").exists():
        print(
            f"No fetched data at {org_dir}. Run `iati-scout fetch --org-id {settings.org_id}` first.",
            file=sys.stderr,
        )
        return 1

    config = load_rule_config()
    codes = [c.strip() for c in args.rules.split(",")] if args.rules else None
    severity = Severity(args.severity) if args.severity else None
    try:
        rules = select_rules(config, codes=codes, severity=severity)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    dataset = load_dataset(org_dir, settings.org_id)
    logging.getLogger(__name__).info(
        "Loaded %d activities for %s; running %d rule(s)", len(dataset), settings.org_id, len(rules)
    )
    findings = run_checks(dataset, config, rules)

    out_dir = (
        Path(args.out_dir) if args.out_dir else settings.data_dir.parent / "quality" / settings.org_id
    )
    paths = write_reports(findings, rules, settings.org_id, len(dataset), out_dir)

    errors = sum(1 for f in findings if f.severity == Severity.ERROR)
    warnings = len(findings) - errors
    print(f"{errors} error(s), {warnings} warning(s) across {len(dataset)} activities")
    print(f"Reports written to {paths['summary'].parent}")

    if not args.no_export:
        manifest_path = org_dir / "manifest.json"
        raw_manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        )
        export_paths = write_export(findings, rules, config, dataset, out_dir, raw_manifest)
        print(f"Dashboard export written to {export_paths['meta'].parent}")

    return 0


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
