"""Fetch the official IATI Validator report for a publisher's documents.

Two hops, both verified 2026-09-19:

1. **IATI Registry** (CKAN) — which documents does this publisher publish?
   ``GET https://iatiregistry.org/api/3/action/package_search?fq=publisher_iati_id:<org_id>``

   The Registry runs a CKAN *compatibility layer*, not full CKAN: the error
   response states that only ``organization``, ``owner_org``,
   ``publisher_iati_id`` and ``extras_filetype`` are accepted inside ``q``/``fq``.
   The value must **not** be wrapped in quotes — ``publisher_iati_id:"X"``
   silently returns zero results while ``publisher_iati_id:X`` matches. A
   publisher commonly has more than one document (RVO publishes two activity
   files), so every dataset is resolved, not just the first.

2. **IATI Validator v2** — the stored report for one of those documents:
   ``GET https://api.iatistandard.org/validator/report?id=<registry_id>``
   with an ``Ocp-Apim-Subscription-Key`` header. The same APIM subscription
   key that the Datastore uses covers this API.

   The report is *pre-computed* by IATI: this endpoint only reads it back, so
   the call is cheap and the result reflects whenever IATI last crawled the
   document (there is no way to force a refresh through this route). A
   document the validator has not yet processed returns 404.

Report shape (IATI Validator API Contract, apiVersion 2.5.0)::

    {registry_hash, registry_id, registry_name, document_url, valid,
     report: {valid, fileType, iatiVersion, rulesetCommitSha, codelistCommitSha,
              orgIdPrefixFileName, apiVersion,
              summary: {critical, error, warning, advisory},
              errors: [{identifier, title,
                        errors: [{category,
                                  errors: [{id, severity, message, context, details?}]}]}]}}
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

REGISTRY_BASE_URL = "https://iatiregistry.org/api/3/action"
VALIDATOR_BASE_URL = "https://api.iatistandard.org/validator"
MAX_RETRIES = 4
RETRY_BACKOFF_BASE = 2.0
TIMEOUT = 120


class ValidatorError(Exception):
    """Raised when the Registry or Validator API returns an unrecoverable error."""


@dataclass(frozen=True)
class RegistryDataset:
    """One document a publisher has registered on the IATI Registry."""

    registry_id: str
    registry_name: str
    document_url: str
    file_type: str | None
    registry_hash: str | None

    @classmethod
    def from_package(cls, package: dict[str, Any]) -> RegistryDataset | None:
        resources = package.get("resources") or []
        if not resources:
            return None
        extras = {e.get("key"): e.get("value") for e in package.get("extras") or []}
        return cls(
            registry_id=package.get("id", ""),
            registry_name=package.get("name", ""),
            document_url=resources[0].get("url", ""),
            file_type=extras.get("filetype"),
            registry_hash=resources[0].get("hash") or None,
        )


class ValidatorClient:
    """Reads published validation reports; does not submit documents for validation."""

    def __init__(
        self,
        api_key: str,
        validator_base_url: str = VALIDATOR_BASE_URL,
        registry_base_url: str = REGISTRY_BASE_URL,
        session: requests.Session | None = None,
    ) -> None:
        self.validator_base_url = validator_base_url.rstrip("/")
        self.registry_base_url = registry_base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers["Ocp-Apim-Subscription-Key"] = api_key

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT)
            except requests.RequestException as exc:  # network-level failure
                last_exc = exc
            else:
                if response.status_code == 404:
                    raise ValidatorError(f"Not found: {url} {params}")
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ValidatorError(f"{url} returned non-JSON content") from exc
                if response.status_code not in (429, 500, 502, 503, 504):
                    raise ValidatorError(
                        f"{url} returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                last_exc = ValidatorError(f"HTTP {response.status_code}")
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE**attempt
                logger.warning("%s failed (%s); retrying in %.0fs", url, last_exc, wait)
                time.sleep(wait)
        raise ValidatorError(f"{url} failed after {MAX_RETRIES} attempts: {last_exc}")

    def find_datasets(self, org_id: str, file_type: str = "activity") -> list[RegistryDataset]:
        """Every document `org_id` has registered, newest Registry entry first.

        `file_type` filters to activity (vs. organisation) files; pass None to keep all.
        """
        payload = self._get(
            f"{self.registry_base_url}/package_search",
            # Unquoted value: the Registry's CKAN compatibility layer does not
            # match when the value is wrapped in double quotes.
            {"fq": f"publisher_iati_id:{org_id}", "rows": 1000},
        )
        result = payload.get("result") or {}
        datasets = []
        for package in result.get("results") or []:
            dataset = RegistryDataset.from_package(package)
            if dataset is None or not dataset.document_url:
                continue
            if file_type and dataset.file_type and dataset.file_type != file_type:
                continue
            datasets.append(dataset)
        if not datasets:
            raise ValidatorError(
                f"The IATI Registry lists no {file_type or ''} documents for {org_id}. "
                "Check the organisation identifier at https://iatiregistry.org/publisher."
            )
        return datasets

    def fetch_report(self, dataset: RegistryDataset) -> dict[str, Any]:
        """The stored validation report for one registered document."""
        return self._get(f"{self.validator_base_url}/report", {"id": dataset.registry_id})

    def fetch_reports(self, org_id: str) -> list[dict[str, Any]]:
        """A report per activity document the publisher has registered.

        A document the validator has not processed yet is logged and skipped
        rather than failing the run: one missing file should not hide the
        findings in the others.
        """
        reports = []
        for dataset in self.find_datasets(org_id):
            try:
                report = self.fetch_report(dataset)
            except ValidatorError as exc:
                logger.warning(
                    "No validation report for %s (%s): %s",
                    dataset.registry_name,
                    dataset.document_url,
                    exc,
                )
                continue
            summary = (report.get("report") or {}).get("summary") or {}
            logger.info(
                "%s: %s (critical=%s error=%s warning=%s advisory=%s)",
                dataset.registry_name,
                "valid" if report.get("valid") else "INVALID",
                summary.get("critical", 0),
                summary.get("error", 0),
                summary.get("warning", 0),
                summary.get("advisory", 0),
            )
            reports.append(report)
        if not reports:
            raise ValidatorError(
                f"The validator has no stored report for any document of {org_id}. "
                "IATI validates registered documents on its own schedule; try again later."
            )
        return reports


def write_reports(reports: list[dict[str, Any]], org_id: str, out_dir: Path) -> Path:
    """Cache the raw reports under `out_dir/<org_id>/`, one file per document.

    Kept verbatim so a `check` run is reproducible offline and so the exact
    ruleset/codelist commit each report was produced against stays auditable.
    """
    org_dir = out_dir / org_id
    org_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "org_id": org_id,
        "fetched_at": datetime.now(UTC).isoformat(),
        "documents": [],
    }
    for report in reports:
        name = report.get("registry_name") or report.get("registry_id") or "report"
        path = org_dir / f"{name}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        inner = report.get("report") or {}
        manifest["documents"].append(
            {
                "registry_name": name,
                "registry_id": report.get("registry_id"),
                "registry_hash": report.get("registry_hash"),
                "document_url": report.get("document_url"),
                "valid": report.get("valid"),
                "file": path.name,
                "iati_version": inner.get("iatiVersion"),
                "api_version": inner.get("apiVersion"),
                "ruleset_commit_sha": inner.get("rulesetCommitSha"),
                "codelist_commit_sha": inner.get("codelistCommitSha"),
                "summary": inner.get("summary") or {},
            }
        )
    manifest_path = org_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def load_reports(org_id: str, out_dir: Path) -> list[dict[str, Any]]:
    """Read back the cached reports written by `write_reports`. Empty if never fetched."""
    manifest_path = out_dir / org_id / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reports = []
    for doc in manifest.get("documents", []):
        path = out_dir / org_id / doc["file"]
        if path.exists():
            reports.append(json.loads(path.read_text(encoding="utf-8")))
    return reports


def dataset_summary(datasets: list[RegistryDataset]) -> list[dict[str, Any]]:
    return [asdict(d) for d in datasets]
