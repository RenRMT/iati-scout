# IATI Scout <a href="https://github.com/RenRMT/iati-scout"><img src="docs/figures/logo_dark.png" align="right" height="100" /></a>

A small Python app for retrieving and analysing [IATI](https://iatistandard.org/) (International
Aid Transparency Initiative) data for a given organisation.

## Status

Two commands so far:

- `iati-scout fetch` pulls all `activity`, `transaction`, and `budget` records for one configurable
  IATI organisation identifier from the
  [IATI Datastore](https://iatistandard.org/en/iati-tools-and-resources/iati-datastore/) API and
  stores them as JSON Lines files in the project directory.
- `iati-scout check` runs a catalogue of **data-quality rules** over the fetched data and writes
  findings (JSONL, CSV, Markdown summary). The rules go beyond schema/codelist validation: they look
  for logical inconsistencies between fields (errors) and combinations that suggest a problem
  worth a human look (warnings).

Data refresh strategies and a UI are out of scope for now; the findings format is designed so a
dashboard can be built on it later.

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

## Data-quality checks

```
python -m iati_scout check --org-id NL-KVK-27378529
python -m iati_scout check --list-rules                 # print the catalogue
python -m iati_scout check --rules E-A01,W-B14          # run a subset
python -m iati_scout check --severity error             # errors only
```

No API key is needed; `check` reads `data/raw/<org_id>/` written by `fetch`.

### Rule catalogue

Codes are `E-<section><nn>` for **errors** (deterministic logical inconsistencies; should be
fixed) and `W-<section><nn>` for **warnings** (patterns that indicate a likely issue; need
follow-up). Sections:

| Section | Covers | Examples |
|---|---|---|
| A | Activity dates & status | actual end before actual start; status Implementation but planned end long passed |
| B | Financial consistency | negative budgets; budget period > 1 year; disbursed more than committed; transactions outside activity dates; receiver = reporting org |
| C | Classification | sector/country percentages ≠ 100; gender sector without gender marker; home country as recipient |
| D | Hierarchy & relations | related activity not in dataset; child dates outside parent dates; identifier published twice |
| E | Organisations | no funding/accountable org; same org twice in one role; org type "Other" |
| F | Text & locations | unparseable coordinates; location in home country while recipient differs; truncated descriptions |
| G | Results | non-numeric indicator values; closed activity without results |
| H | Identifier hygiene | activity id equals reporting-org id; identifier whitespace or forbidden symbols |

Run `--list-rules` for the full list with titles. Rules are pure functions in
[src/iati_scout/quality/rules/](src/iati_scout/quality/rules/); adding one means registering a
function with `@rule(code, severity, title)` and adding a test.

### Coverage of the IATI standard ruleset

Sections A–H also cover most of the [IATI standard
ruleset](https://iatistandard.org/en/iati-standard/203/rulesets/standard-ruleset/) — the
official set of cross-field validation rules (distinct from codelist/schema validation, which
the IATI Validator already covers before data is published). Rules ported from it carry the
matching ruleset ID in their `description` (see `--list-rules` or `rules.json` in the dashboard
export). Deliberately not implemented, because this tool doesn't fetch or model the data they'd
need:

- Rules scoped to the `iati-organisations` registration file (this tool only processes
  `activity`/`transaction`/`budget` data for one reporting organisation)
- The approved reporting-organisation agency-code prefix check (needs an external codelist)
- Result-level-vs-indicator-level reference placement, and sector/recipient-country consistency
  between activity and transaction level — the Datastore's flattened schema loses the nesting
  (or, for the latter, denormalizes the activity's own sector/country onto every transaction row,
  making a genuine per-transaction override indistinguishable from inherited data)
- A handful of niche identifier fields (`other-identifier`/`owner-org`, transaction-level
  `provider-activity-id`/`receiver-activity-id`)

### Configuration: `rules.toml`

[rules.toml](rules.toml) holds thresholds (staleness, budget period limits, outlier percentile, …)
and per-rule switches:

```toml
[rules."W-C09"]
enabled = false    # skip entirely
systemic = true    # keep, but mark as a known organisation-wide pattern
```

"Systemic" findings are ones caused by how the publisher's source system exports data rather
than by individual activities (e.g. de-commitments published as negative budgets). They stay in
the output, flagged, so a report can collapse them to a count instead of thousands of rows.

### Output

```
data/quality/<org_id>/
├── findings.jsonl   # canonical: one self-contained finding per line
├── findings.csv     # same, flattened for spreadsheets
├── summary.md       # counts per rule + sample findings with links
└── export/          # machine-readable contract for the dashboard (see below)
```

Every finding carries: rule code/severity/title, activity identifier and title, a message that
quotes the offending values, a structured `evidence` dict with those values, an `item` locator
for transaction/budget-level findings, `related` activities (e.g. the parent, with its own link),
and `urls` — a [d-portal](https://d-portal.iatistandard.org/) link to the activity plus the
Datastore query.

`check` also writes `data/quality/<org_id>/export/` (skip with `--no-export`) — a smaller,
columnar version of the same findings (Parquet + JSON) for the dashboard below. See
[src/iati_scout/quality/export.py](src/iati_scout/quality/export.py) for the exact file contract.

## Dashboard

An [Observable Framework](https://observablehq.com/framework/) static site in
[dashboard/](dashboard/) visualises the `export/` output: an overview with KPIs and a findings
chart, a rule explorer, a filterable findings table, and an activity explorer. It is a **separate
layer** — it only reads the `export/` files and never imports `iati_scout`. See
[dashboard/README.md](dashboard/README.md) for how to run it (`cd dashboard && npm install && npm
run dev`) and its data contract.

### Caveat: nested elements

The Datastore's flattened JSON keeps sibling arrays aligned for flat repeats (transactions,
budgets, sectors, dates, participating orgs) but loses nesting for result → indicator → period
and document-link. Section G rules are therefore activity-level; rules that need "this period
belongs to this indicator" would require the `/iati` XML endpoint.

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
