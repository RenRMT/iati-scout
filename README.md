# iati-scout

A small Python app for retrieving and analysing [IATI](https://iatistandard.org/) (International
Aid Transparency Initiative) data for a given organisation.

## Status

Current scope: **retrieval only**. `iati-scout fetch` pulls all `activity`, `transaction`, and
`budget` records for one configurable IATI organisation identifier from the
[IATI Datastore](https://iatistandard.org/en/iati-tools-and-resources/iati-datastore/) API and
stores them as JSON Lines files in the project directory. Data refresh strategies and
transformations/analysis are out of scope for now.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in your API key:

```
copy .env.example .env
```

- `IATI_API_KEY`: subscription key from the
  [IATI Developer Portal](https://developer.iatistandard.org/) (Datastore product, header
  `Ocp-Apim-Subscription-Key`).
- `IATI_ORG_ID`: default organisation to fetch, e.g. `NL-KVK-27378529`. Can also be set via
  `org_id` in `config.toml`, or overridden per run with `--org-id`.

Non-secret settings (collections to fetch, page size, request throttling, output directory,
API base URL) live in [config.toml](config.toml).

## Usage

```
python -m iati_scout fetch --org-id NL-KVK-27378529
```

Or rely on `IATI_ORG_ID` / `config.toml`:

```
python -m iati_scout fetch
```

Options:

- `--org-id`: IATI organisation identifier (overrides env/config).
- `--collections`: comma-separated subset of `activity,transaction,budget`.
- `--data-dir`: output directory (default: `data/raw`, from `config.toml`).
- `-v` / `--verbose`: debug logging.

### Output

```
data/raw/<org_id>/
├── activity.jsonl
├── transaction.jsonl
├── budget.jsonl
└── manifest.json
```

Each `.jsonl` file has one Datastore document per line (raw, flattened Solr JSON — one row per
activity/transaction/budget). `manifest.json` records the fetch time, tool version, and per-collection
`num_found` (as reported by the Datastore) vs. `written` counts, so a mismatch is easy to spot.

`data/` is gitignored — fetched data stays local to your machine.

## Development

```
pytest
ruff check src tests
```

Datastore requests are mocked in tests (no network access, no API key required).

## Notes on the Datastore API

- Base URL: `https://api.iatistandard.org/datastore/{activity,transaction,budget}/select`
  (Solr `select` handler).
- Filtered by reporting organisation with `q=reporting_org_ref:"<ORG_ID>"`.
- Deep pagination uses Solr `cursorMark`, which requires a sort ending in a unique tie-breaker;
  this project uses `sort=iati_identifier asc, id asc`.
- The exploratory API tier has a low, undocumented rate limit with no `Retry-After` header on
  429s, so the client throttles proactively (`min_request_interval` in `config.toml`) and retries
  failed requests with exponential backoff.
