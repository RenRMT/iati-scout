"""Tests for the Registry lookup and Validator report client."""

import json

import pytest
import responses

from iati_scout.validator import (
    REGISTRY_BASE_URL,
    VALIDATOR_BASE_URL,
    RegistryDataset,
    ValidatorClient,
    ValidatorError,
    load_reports,
    write_reports,
)

ORG_ID = "NL-KVK-27378529"

PACKAGE_SEARCH = {
    "result": {
        "count": 3,
        "results": [
            {
                "id": "d364eabc",
                "name": "rvo-01",
                "extras": [{"key": "filetype", "value": "activity"}],
                "resources": [
                    {"url": "https://projects.rvo.nl/opendata/iati.xml", "hash": "cfd2603d"}
                ],
            },
            {
                "id": "9f1c2b77",
                "name": "rvo-activities",
                "extras": [{"key": "filetype", "value": "activity"}],
                "resources": [{"url": "https://example.org/rvo-activities.xml", "hash": "7c094d44"}],
            },
            {
                "id": "org-file",
                "name": "rvo-org",
                "extras": [{"key": "filetype", "value": "organisation"}],
                "resources": [{"url": "https://projects.rvo.nl/opendata/org.xml"}],
            },
        ],
    }
}


def _report(name: str, errors: int = 1) -> dict:
    return {
        "registry_name": name,
        "registry_id": f"id-{name}",
        "registry_hash": f"hash-{name}",
        "document_url": f"https://example.org/{name}.xml",
        "valid": True,
        "report": {
            "valid": True,
            "fileType": "iati-activities",
            "iatiVersion": "2.03",
            "apiVersion": "2.5.0",
            "rulesetCommitSha": "2cd1a14f6c",
            "codelistCommitSha": "ba76c3118d",
            "summary": {"critical": 0, "error": errors, "warning": 0, "advisory": 0},
            "errors": [],
        },
    }


def _client() -> ValidatorClient:
    return ValidatorClient(api_key="key")


@responses.activate
def test_find_datasets_filters_to_activity_files():
    responses.add(responses.GET, f"{REGISTRY_BASE_URL}/package_search", json=PACKAGE_SEARCH)

    datasets = _client().find_datasets(ORG_ID)

    assert [d.registry_name for d in datasets] == ["rvo-01", "rvo-activities"]
    assert datasets[0].document_url == "https://projects.rvo.nl/opendata/iati.xml"
    assert datasets[0].registry_hash == "cfd2603d"
    # The Registry's CKAN compatibility layer returns nothing for a quoted
    # value, so the filter must be sent unquoted.
    assert responses.calls[0].request.params["fq"] == f"publisher_iati_id:{ORG_ID}"


@responses.activate
def test_find_datasets_raises_when_the_publisher_is_unknown():
    responses.add(
        responses.GET, f"{REGISTRY_BASE_URL}/package_search", json={"result": {"results": []}}
    )
    with pytest.raises(ValidatorError, match="no activity documents"):
        _client().find_datasets("XX-NOT-A-PUBLISHER")


@responses.activate
def test_fetch_report_asks_by_registry_id():
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", json=_report("rvo-01"))
    dataset = RegistryDataset("d364eabc", "rvo-01", "https://x/iati.xml", "activity", None)

    report = _client().fetch_report(dataset)

    assert report["registry_name"] == "rvo-01"
    assert responses.calls[0].request.params["id"] == "d364eabc"
    assert responses.calls[0].request.headers["Ocp-Apim-Subscription-Key"] == "key"


@responses.activate
def test_fetch_reports_skips_a_document_with_no_stored_report():
    """One unvalidated file must not hide the findings in the publisher's other files."""
    responses.add(responses.GET, f"{REGISTRY_BASE_URL}/package_search", json=PACKAGE_SEARCH)
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", json=_report("rvo-01"))
    responses.add(
        responses.GET,
        f"{VALIDATOR_BASE_URL}/report",
        json={"client_error": "The requested report does not exist."},
        status=404,
    )

    reports = _client().fetch_reports(ORG_ID)

    assert [r["registry_name"] for r in reports] == ["rvo-01"]


@responses.activate
def test_fetch_reports_raises_when_no_document_has_a_report():
    responses.add(responses.GET, f"{REGISTRY_BASE_URL}/package_search", json=PACKAGE_SEARCH)
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", status=404)
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", status=404)

    with pytest.raises(ValidatorError, match="no stored report"):
        _client().fetch_reports(ORG_ID)


@responses.activate
def test_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr("iati_scout.validator.time.sleep", lambda _: None)
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", status=429)
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", json=_report("rvo-01"))
    dataset = RegistryDataset("d364eabc", "rvo-01", "https://x/iati.xml", "activity", None)

    assert _client().fetch_report(dataset)["registry_name"] == "rvo-01"
    assert len(responses.calls) == 2


@responses.activate
def test_client_error_is_not_retried(monkeypatch):
    monkeypatch.setattr("iati_scout.validator.time.sleep", lambda _: None)
    responses.add(responses.GET, f"{VALIDATOR_BASE_URL}/report", status=401)
    dataset = RegistryDataset("d364eabc", "rvo-01", "https://x/iati.xml", "activity", None)

    with pytest.raises(ValidatorError, match="HTTP 401"):
        _client().fetch_report(dataset)
    assert len(responses.calls) == 1


def test_reports_round_trip_through_the_cache(tmp_path):
    reports = [_report("rvo-01", errors=10332), _report("rvo-activities", errors=2)]

    manifest_path = write_reports(reports, ORG_ID, tmp_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["org_id"] == ORG_ID
    assert [d["registry_name"] for d in manifest["documents"]] == ["rvo-01", "rvo-activities"]
    # The ruleset the report was produced against is recorded, so an old run
    # stays auditable after IATI moves the ruleset on.
    assert manifest["documents"][0]["ruleset_commit_sha"] == "2cd1a14f6c"
    assert manifest["documents"][0]["summary"]["error"] == 10332

    assert load_reports(ORG_ID, tmp_path) == reports


def test_load_reports_is_empty_when_never_fetched(tmp_path):
    assert load_reports(ORG_ID, tmp_path) == []
