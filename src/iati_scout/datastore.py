"""Client for the IATI Datastore v3 Solr-backed select API.

API reference (verified 2026-09-11 against
https://api.iatistandard.org/datastore/{collection}/select):

- Auth: header ``Ocp-Apim-Subscription-Key: <key>``.
- Collections: ``activity``, ``transaction``, ``budget`` (one row per
  activity/transaction/budget respectively; all other fields are flattened
  arrays alongside it).
- Filtering by reporting organisation: ``q=reporting_org_ref:"<ORG_ID>"``.
- Deep pagination requires Solr's cursorMark, which in turn requires a sort
  that ends in a unique tie-breaker field. ``iati_identifier`` alone is not
  unique (repeated once per transaction/budget row), so the sort must be
  ``iati_identifier asc, id asc`` — ``id`` is the collection's internal
  Solr uniqueKey (not present in the returned documents, but valid as a
  sort key). Pass ``cursorMark=*`` on the first request and thereafter the
  ``nextCursorMark`` from the previous response; pagination is complete once
  ``nextCursorMark`` repeats.
- The exploratory API tier enforces a low, undocumented rate limit and
  returns plain HTTP 429 with no ``Retry-After`` header, so this client
  throttles proactively and retries with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import requests

logger = logging.getLogger(__name__)

SORT = "iati_identifier asc, id asc"
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2.0


class DatastoreError(Exception):
    """Raised when the Datastore API returns an unrecoverable error."""


class DatastoreClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        rows_per_page: int = 500,
        min_request_interval: float = 1.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rows_per_page = rows_per_page
        self.min_request_interval = min_request_interval
        self.session = session or requests.Session()
        self.session.headers["Ocp-Apim-Subscription-Key"] = api_key
        self._last_request_time: float | None = None

    def _throttle(self) -> None:
        if self._last_request_time is None:
            return
        elapsed = time.monotonic() - self._last_request_time
        wait = self.min_request_interval - elapsed
        if wait > 0:
            time.sleep(wait)

    def _get(self, collection: str, params: dict) -> dict:
        url = f"{self.base_url}/{collection}/select"
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            self._last_request_time = time.monotonic()
            try:
                response = self.session.get(url, params=params, timeout=60)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Request error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after
                        else RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    )
                    logger.warning(
                        "HTTP %d from %s (attempt %d/%d), retrying in %.1fs",
                        response.status_code,
                        collection,
                        attempt,
                        MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise DatastoreError(
                    f"Datastore returned HTTP {response.status_code} for {collection}: "
                    f"{response.text[:500]}"
                )
        raise DatastoreError(
            f"Datastore request for {collection} failed after {MAX_RETRIES} attempts"
        ) from last_exc

    def iter_docs(
        self,
        collection: str,
        org_id: str,
        stats: dict | None = None,
    ) -> Iterator[dict]:
        """Yield every document for `org_id` in `collection`, paging via cursorMark.

        If `stats` is given, sets stats["num_found"] to the Solr-reported
        total after the first page.
        """
        cursor_mark = "*"
        params = {
            "q": f'reporting_org_ref:"{org_id}"',
            "rows": self.rows_per_page,
            "wt": "json",
            "sort": SORT,
        }
        first_page = True
        while True:
            params["cursorMark"] = cursor_mark
            payload = self._get(collection, params)
            response = payload.get("response", {})
            docs = response.get("docs", [])

            if first_page and stats is not None:
                stats["num_found"] = response.get("numFound", 0)
            first_page = False

            yield from docs

            next_cursor_mark = payload.get("nextCursorMark")
            if not next_cursor_mark or next_cursor_mark == cursor_mark:
                break
            cursor_mark = next_cursor_mark
