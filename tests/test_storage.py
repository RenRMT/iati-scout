import json
from pathlib import Path

from iati_scout.storage import fetch_organisation, write_jsonl


def test_write_jsonl_writes_one_doc_per_line(tmp_path: Path):
    docs = [{"a": 1}, {"a": 2}]
    out_path = tmp_path / "sub" / "out.jsonl"

    count = write_jsonl(docs, out_path)

    assert count == 2
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == docs


def test_write_jsonl_does_not_leave_tmp_file(tmp_path: Path):
    out_path = tmp_path / "out.jsonl"
    write_jsonl([{"a": 1}], out_path)

    assert out_path.exists()
    assert not out_path.with_suffix(out_path.suffix + ".tmp").exists()


class FakeClient:
    def __init__(self, data: dict[str, list[dict]]):
        self.data = data

    def iter_docs(self, collection, org_id, stats=None):
        docs = self.data[collection]
        if stats is not None:
            stats["num_found"] = len(docs)
        yield from docs


def test_fetch_organisation_writes_jsonl_and_manifest(tmp_path: Path):
    client = FakeClient(
        {
            "activity": [{"iati_identifier": "X-1"}],
            "transaction": [{"iati_identifier": "X-1"}, {"iati_identifier": "X-1"}],
        }
    )

    manifest = fetch_organisation(client, "TEST-ORG", ("activity", "transaction"), tmp_path)

    activity_file = tmp_path / "TEST-ORG" / "activity.jsonl"
    transaction_file = tmp_path / "TEST-ORG" / "transaction.jsonl"
    manifest_file = tmp_path / "TEST-ORG" / "manifest.json"

    assert activity_file.exists()
    assert len(activity_file.read_text().splitlines()) == 1
    assert transaction_file.exists()
    assert len(transaction_file.read_text().splitlines()) == 2
    assert manifest_file.exists()

    assert manifest["org_id"] == "TEST-ORG"
    assert manifest["collections"]["activity"] == {
        "num_found": 1,
        "written": 1,
        "file": "TEST-ORG/activity.jsonl",
    }
    assert manifest["collections"]["transaction"]["written"] == 2

    on_disk_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert on_disk_manifest == manifest
