"""Command-line entry point: `python -m iati_scout <fetch|validate|check> [options]`."""

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

    validate_parser = subparsers.add_parser(
        "validate",
        help="Fetch the official IATI Validator report for the organisation's documents",
    )
    validate_parser.add_argument(
        "--org-id", help="IATI organisation identifier, e.g. NL-KVK-27378529"
    )
    validate_parser.add_argument(
        "--validation-dir",
        help="Where to cache the reports (default: from config.toml)",
    )
    validate_parser.add_argument(
        "--list-documents",
        action="store_true",
        help="List the organisation's registered documents and exit, without fetching reports",
    )
    validate_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    check_parser = subparsers.add_parser(
        "check",
        help="Merge the official validation report with iati-scout's additional rules",
    )
    check_parser.add_argument(
        "--org-id", help="IATI organisation identifier, e.g. NL-KVK-27378529"
    )
    check_parser.add_argument(
        "--data-dir", help="Directory holding data/raw/<org_id> (default: from config.toml)"
    )
    check_parser.add_argument(
        "--validation-dir", help="Directory holding cached validator reports"
    )
    check_parser.add_argument(
        "--out-dir", help="Where to write reports (default: <data-dir>/../quality/<org_id>)"
    )
    check_parser.add_argument(
        "--rules", help="Comma-separated scout rule codes to run (default: all enabled)"
    )
    check_parser.add_argument(
        "--category",
        help="Only run scout rules in this official category (e.g. financial, relations)",
    )
    check_parser.add_argument(
        "--list-rules", action="store_true", help="Print the scout rule catalogue and exit"
    )
    check_parser.add_argument(
        "--no-validator",
        action="store_true",
        help="Skip the official validation report; report only iati-scout's own findings",
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
    if args.command == "validate":
        return _validate(args)
    if args.command == "check":
        return _check(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _validate(args: argparse.Namespace) -> int:
    from iati_scout.validator import ValidatorClient, ValidatorError, write_reports

    try:
        settings = load_settings(org_id=args.org_id)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    client = ValidatorClient(
        api_key=settings.api_key,
        validator_base_url=settings.validator_base_url,
        registry_base_url=settings.registry_base_url,
    )

    try:
        if args.list_documents:
            for dataset in client.find_datasets(settings.org_id):
                print(f"{dataset.registry_name}\t{dataset.file_type}\t{dataset.document_url}")
            return 0
        reports = client.fetch_reports(settings.org_id)
    except ValidatorError as exc:
        print(f"Validation fetch failed: {exc}", file=sys.stderr)
        return 1

    validation_dir = (
        Path(args.validation_dir) if args.validation_dir else settings.validation_dir
    )
    manifest_path = write_reports(reports, settings.org_id, validation_dir)

    totals: dict[str, int] = {}
    for report in reports:
        for key, value in ((report.get("report") or {}).get("summary") or {}).items():
            totals[key] = totals.get(key, 0) + value
    counts = ", ".join(f"{v} {k}" for k, v in sorted(totals.items()) if v)
    valid = all(r.get("valid") for r in reports)
    print(
        f"{len(reports)} document(s), {'valid' if valid else 'INVALID'}"
        f"{f': {counts}' if counts else ''}"
    )
    print(f"Reports cached in {manifest_path.parent}")
    return 0


def _check(args: argparse.Namespace) -> int:
    import json

    from iati_scout.quality.export import write_export
    from iati_scout.quality.findings import Category, Source
    from iati_scout.quality.model import load_dataset
    from iati_scout.quality.registry import all_rules, load_rule_config
    from iati_scout.quality.report import count_by_severity, write_reports
    from iati_scout.quality.runner import findings_from_reports, run_checks, select_rules
    from iati_scout.validator import load_reports

    if args.list_rules:
        for spec in all_rules():
            print(
                f"{spec.code}  {spec.severity.value:8s}  {spec.category.value:15s}  "
                f"[{spec.weight}]  {spec.title}"
            )
            if spec.description:
                print(f"           {spec.description}")
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
    try:
        category = Category(args.category) if args.category else None
    except ValueError:
        print(
            f"Unknown category {args.category!r}. Valid: "
            f"{', '.join(c.value for c in Category)}",
            file=sys.stderr,
        )
        return 1
    try:
        rules = select_rules(config, codes=codes, category=category)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    validation_dir = Path(args.validation_dir) if args.validation_dir else settings.validation_dir
    validator_reports = [] if args.no_validator else load_reports(settings.org_id, validation_dir)
    if not validator_reports and not args.no_validator:
        print(
            f"No cached validation report for {settings.org_id} in {validation_dir}. "
            f"Run `iati-scout validate --org-id {settings.org_id}` first, "
            "or pass --no-validator to report only iati-scout's own findings.",
            file=sys.stderr,
        )
        return 1

    dataset = load_dataset(org_dir, settings.org_id)
    logging.getLogger(__name__).info(
        "Loaded %d activities for %s; running %d scout rule(s)",
        len(dataset),
        settings.org_id,
        len(rules),
    )
    findings = findings_from_reports(validator_reports) + run_checks(dataset, config, rules)

    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else settings.data_dir.parent / "quality" / settings.org_id
    )
    known_identifiers = {a.identifier for a in dataset}
    paths = write_reports(
        findings,
        rules,
        settings.org_id,
        len(dataset),
        out_dir,
        validator_reports,
        known_identifiers,
    )

    per_source = {
        s.value: sum(1 for f in findings if f.source == s) for s in Source
    }
    counts = ", ".join(f"{v} {k}" for k, v in count_by_severity(findings).items())
    print(f"{len(findings)} finding(s) across {len(dataset)} activities: {counts}")
    print(
        f"  {per_source[Source.VALIDATOR.value]} from the official IATI validator, "
        f"{per_source[Source.SCOUT.value]} from iati-scout rules"
    )
    print(f"Reports written to {paths['report'].parent}")

    if not args.no_export:
        manifest_path = org_dir / "manifest.json"
        raw_manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        )
        export_paths = write_export(
            findings, rules, config, dataset, out_dir, raw_manifest, validator_reports
        )
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
