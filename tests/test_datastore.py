import responses

from iati_scout.datastore import DatastoreClient, DatastoreError

BASE_URL = "https://api.iatistandard.org/datastore"


def _page(docs, next_cursor, num_found):
    return {
        "response": {"numFound": num_found, "start": 0, "docs": docs},
        "nextCursorMark": next_cursor,
    }


@responses.activate
def test_iter_docs_paginates_until_cursor_repeats():
    responses.add(
        responses.GET,
        f"{BASE_URL}/activity/select",
        json=_page([{"iati_identifier": "A-1"}, {"iati_identifier": "A-2"}], "cursor2", 3),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/activity/select",
        json=_page([{"iati_identifier": "A-3"}], "cursor2", 3),
        status=200,
    )

    client = DatastoreClient(
        api_key="key", base_url=BASE_URL, rows_per_page=2, min_request_interval=0
    )
    stats: dict = {}
    docs = list(client.iter_docs("activity", "TEST-ORG", stats=stats))

    assert [d["iati_identifier"] for d in docs] == ["A-1", "A-2", "A-3"]
    assert stats["num_found"] == 3
    assert len(responses.calls) == 2


@responses.activate
def test_iter_docs_sends_expected_query_params():
    responses.add(
        responses.GET,
        f"{BASE_URL}/activity/select",
        json=_page([], "*", 0),
        status=200,
    )

    client = DatastoreClient(
        api_key="key", base_url=BASE_URL, rows_per_page=50, min_request_interval=0
    )
    list(client.iter_docs("activity", "NL-KVK-27378529"))

    request = responses.calls[0].request
    assert "q=reporting_org_ref%3A%22NL-KVK-27378529%22" in request.url
    assert "cursorMark=%2A" in request.url
    assert "sort=iati_identifier+asc%2C+id+asc" in request.url
    assert request.headers["Ocp-Apim-Subscription-Key"] == "key"


@responses.activate
def test_retries_on_429_then_succeeds():
    responses.add(responses.GET, f"{BASE_URL}/activity/select", status=429)
    responses.add(
        responses.GET,
        f"{BASE_URL}/activity/select",
        json=_page([{"iati_identifier": "A-1"}], "*", 1),
        status=200,
    )

    client = DatastoreClient(
        api_key="key", base_url=BASE_URL, rows_per_page=10, min_request_interval=0
    )
    # Avoid a real sleep for the backoff in this test.
    import iati_scout.datastore as datastore_module

    datastore_module.time.sleep = lambda _seconds: None

    docs = list(client.iter_docs("activity", "TEST-ORG"))

    assert [d["iati_identifier"] for d in docs] == ["A-1"]
    assert len(responses.calls) == 2


@responses.activate
def test_raises_datastore_error_on_persistent_failure():
    for _ in range(5):
        responses.add(responses.GET, f"{BASE_URL}/activity/select", status=500)

    client = DatastoreClient(
        api_key="key", base_url=BASE_URL, rows_per_page=10, min_request_interval=0
    )
    import iati_scout.datastore as datastore_module

    datastore_module.time.sleep = lambda _seconds: None

    try:
        list(client.iter_docs("activity", "TEST-ORG"))
        assert False, "expected DatastoreError"
    except DatastoreError:
        pass


@responses.activate
def test_raises_datastore_error_on_client_error():
    responses.add(responses.GET, f"{BASE_URL}/activity/select", status=400, body="bad query")

    client = DatastoreClient(
        api_key="key", base_url=BASE_URL, rows_per_page=10, min_request_interval=0
    )
    try:
        list(client.iter_docs("activity", "TEST-ORG"))
        assert False, "expected DatastoreError"
    except DatastoreError as exc:
        assert "400" in str(exc)
