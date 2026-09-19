# IATI Scout <a href="https://github.com/RenRMT/iati-scout"><img src="docs/figures/logo_dark.png" align="right" height="100" /></a>

A small Python app for retrieving and analysing [IATI](https://iatistandard.org/) (International
Aid Transparency Initiative) data for a given organisation.

## Status

Three commands:

- `iati-scout fetch` pulls all `activity`, `transaction`, and `budget` records for one configurable
  IATI organisation identifier from the
  [IATI Datastore](https://iatistandard.org/en/iati-tools-and-resources/iati-datastore/) API and
  stores them as JSON Lines files in the project directory.
- `iati-scout validate` fetches the **official IATI validation report** for every document the
  organisation has registered, via the [IATI Validator](https://validator.iatistandard.org/) API.
- `iati-scout check` merges that report with iati-scout's **additional** rules — the checks IATI
  does not make — and writes the result in the validator's own report format.

iati-scout does not re-implement the IATI standard ruleset. IATI publishes a validation report for
every registered document; that report is the source of truth for whether data conforms to the
standard. What this tool adds are cross-field and cross-activity checks that a conforming file can
still fail: money that does not add up, children that outlive their parents, closed activities with
no results.

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

## Official IATI validation

```
python -m iati_scout validate --org-id NL-KVK-27378529
python -m iati_scout validate --list-documents          # what does this publisher register?
```

Two hops. First the [IATI Registry](https://iatiregistry.org/) is asked which documents the
organisation publishes (a publisher often has more than one — RVO registers two activity files).
Then the [IATI Validator](https://validator.iatistandard.org/) API is asked for the **stored**
report for each. IATI validates registered documents on its own schedule; this endpoint reads the
result back, so the call is cheap and there is no way to force a refresh through it. A document
IATI has not processed yet is skipped with a warning rather than failing the run.

Reports are cached verbatim under `data/validation/<org_id>/`, one file per document plus a
`manifest.json` recording the `rulesetCommitSha` and `codelistCommitSha` each was produced
against — IATI versions the ruleset independently of this tool, so pinning it is what keeps an
old run auditable.

This uses the same `IATI_API_KEY` as `fetch` (the APIM subscription covers both products).

## Data-quality checks

```
python -m iati_scout check --org-id NL-KVK-27378529
python -m iati_scout check --list-rules                 # print the scout rule catalogue
python -m iati_scout check --rules W-B12,W-B14          # run a subset of scout rules
python -m iati_scout check --category financial         # one official category only
python -m iati_scout check --no-validator               # scout rules only, no report needed
```

`check` reads `data/raw/<org_id>/` (from `fetch`) and `data/validation/<org_id>/` (from
`validate`), and merges the two into one report. No API key is needed.

### What comes from where

| | Source | Severity | Covers |
|---|---|---|---|
| **Standard conformance** | official IATI Validator | `critical` / `error` / `warning` / `advisory` | the [IATI standard ruleset](https://iatistandard.org/en/iati-standard/203/rulesets/standard-ruleset/), codelists, schema |
| **Everything else** | iati-scout rules | always `advisory` | cross-field and cross-activity consistency IATI does not check |

Every scout rule reports as `advisory`: the validator's `error` and `warning` mean *violates the
published IATI standard*, which a heuristic by definition does not. Note that the validator also
emits `advisory` (its 1000.x linked-activity checks), so **severity alone does not identify the
source** — every finding carries a `source` field (`validator` or `scout`) for that. Rule ids
cannot collide either: official ids are dotted numbers (`7.5.3`), scout codes are alphabetic
(`W-B12`).

### Scout rule catalogue

53 rules. The `E-`/`W-` prefix is scout's own confidence signal — `E-` for a deterministic
inconsistency, `W-` for a pattern that needs a human look — exposed as `weight`, since `severity`
is now fixed at `advisory`. Rules are grouped into the official category vocabulary:

| Section | Category | Covers |
|---|---|---|
| A | `iati` | pipeline activity with transactions; implementation status with an actual end date; stale activities |
| B | `financial` | negative budgets; disbursed more than committed; transactions outside activity dates; receiver = reporting org; duplicate and outlier transactions |
| C | `classifications` | gender sector without a gender marker; home country as recipient; missing default classification |
| D | `relations` | related activity not in the dataset; child dates outside parent dates; identifier published twice; child country not in parent's |
| E | `participating` | no funding/accountable org; same org twice in one role; org type "Other" |
| F | `geo` / `information` | unparseable or out-of-range coordinates; location in home country while recipient differs; truncated or duplicated descriptions |
| G | `performance` | closed activity without results; closed activity with targets but no actuals |

Run `--list-rules` for the full list. Rules are pure functions in
[src/iati_scout/quality/rules/](src/iati_scout/quality/rules/); adding one means registering a
function with `@rule(code, category, title)` and adding a test.

### What iati-scout deliberately does not check

Anything in the IATI standard ruleset — that is the validator's job now, and re-implementing a
rule would mean reporting the same violation twice from two sources that can drift apart. A test
([tests/quality/test_all_rules.py](tests/quality/test_all_rules.py)) pins the 26 rule codes that
were removed when this tool switched over, so one cannot quietly come back.

### Configuration: `rules.toml`

[rules.toml](rules.toml) holds thresholds (staleness, budget period limits, outlier percentile, ...)
and per-rule switches for **scout rules only** — the official report is taken as published:

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
data/validation/<org_id>/   # from `validate`
├── <registry-name>.json    # the official report, verbatim, one per document
└── manifest.json           # document urls, hashes, ruleset/codelist commit shas

data/quality/<org_id>/      # from `check`
├── report.json             # canonical: both sources, in the official report format
├── findings.csv            # flattened, one row per finding, for spreadsheets
├── summary.md              # counts and samples for a human
└── export/                 # machine-readable contract for the dashboard (see below)
```

`report.json` follows the [IATI Validator API
Contract](https://cdn.iatistandard.org/prod-iati-website/documents/IATI_Validator_API_Contract.pdf):
the same `report.summary` / `report.errors` shape, nested activity -> category -> error, so
anything that already reads an IATI validation report can read it.

Scout's additions are namespaced rather than mixed in, so a consumer that only knows the official
schema still parses the file correctly:

- a top-level `scout` block with run metadata (org, tool version, per-source counts, the documents
  validated, and any activities that are published but absent from the Datastore);
- per-finding extras under the contract's free-form `details` object — `source`, `rule_title`,
  `systemic`, a structured `evidence` dict quoting the offending values, an `item` locator for
  transaction/budget-level findings, `related` activities, and `urls` (a
  [d-portal](https://d-portal.iatistandard.org/) link plus the Datastore query).

`check` also writes `data/quality/<org_id>/export/` (skip with `--no-export`) — a columnar version
of the same findings (Parquet + JSON) for the dashboard below. See
[src/iati_scout/quality/export.py](src/iati_scout/quality/export.py) for the exact file contract.

## Dashboard

An [Observable Framework](https://observablehq.com/framework/) static site in
[dashboard/](dashboard/) visualises the `export/` output: an overview with KPIs and a findings
chart, a rule explorer, a filterable findings table, and an activity explorer. It is a **separate
layer** — it only reads the `export/` files and never imports `iati_scout`. See
[dashboard/README.md](dashboard/README.md) for how to run it (`cd dashboard && npm install && npm
run dev`) and its data contract.

### Publishing to GitHub Pages

[.github/workflows/deploy-dashboard.yml](.github/workflows/deploy-dashboard.yml) rebuilds the
dashboard from fresh Datastore data and publishes it to GitHub Pages, on a weekly schedule
(Monday 03:00 UTC) or on demand (Actions tab → "Deploy dashboard to GitHub Pages" → Run workflow).
It runs `fetch`, `validate` and `check` to regenerate `export/` from scratch, then
`npm run build`, then deploys `dashboard/dist/` — the site always reflects live IATI Datastore
data and the current official validation report, not a stale snapshot in the repo.

One-time setup:

- **Settings → Pages → Source: GitHub Actions.**
- **Settings → Secrets and variables → Actions → New repository secret**: `IATI_API_KEY` (your
  Datastore subscription key).
- **Settings → Secrets and variables → Actions → Variables → New repository variable**:
  `IATI_ORG_ID` (e.g. `NL-KVK-27378529`).

Framework's build output uses relative asset and page links throughout, so it works unmodified
from GitHub's project-site subpath (`https://<user>.github.io/iati-scout/`) — no `base` config
needed.

### Caveat: two views of the same publisher

The two sources do not read the same bytes. The validator reads the publisher's **XML** directly,
so its findings carry line and column numbers and cover every activity in the file. Scout rules
read the **Datastore's** ingested copy, which can lag behind or drop activities — for RVO, 23
activities appear in the validated XML but not in the Datastore. Those identifiers are listed
under `scout.activities_not_in_datastore` in `report.json` rather than being silently folded into
the totals.

The Datastore's flattened JSON also keeps sibling arrays aligned for flat repeats (transactions,
budgets, sectors, dates, participating orgs) but loses nesting for result → indicator → period
and document-link. Section G rules are therefore activity-level; rules that need "this period
belongs to this indicator" would require the `/iati` XML endpoint. This is one reason to let IATI
run the ruleset: the validator sees the nesting, and this tool does not.

## Development

```
pytest
ruff check src tests
```

Datastore requests are mocked in tests (no network access, no API key required).

## Notes on the IATI APIs

### Validator (`iati-scout validate`)

- Which documents a publisher registers:
  `GET https://iatiregistry.org/api/3/action/package_search?fq=publisher_iati_id:<ORG_ID>`.
  The Registry runs a CKAN *compatibility layer*, not full CKAN — only `organization`,
  `owner_org`, `publisher_iati_id` and `extras_filetype` are accepted inside `q`/`fq`, and the
  value must **not** be quoted: `publisher_iati_id:"X"` silently returns zero results while
  `publisher_iati_id:X` matches.
- The stored report: `GET https://api.iatistandard.org/validator/report?id=<registry_id>` with
  the `Ocp-Apim-Subscription-Key` header. `url`, `hash` and `name` also work as lookup keys.
- The same key is rate-limited like the Datastore's, so `validate` retries 429s with backoff.

### Datastore (`iati-scout fetch`)

- Base URL: `https://api.iatistandard.org/datastore/{activity,transaction,budget}/select`
  (Solr `select` handler).
- Filtered by reporting organisation with `q=reporting_org_ref:"<ORG_ID>"`.
- Deep pagination uses Solr `cursorMark`, which requires a sort ending in a unique tie-breaker;
  this project uses `sort=iati_identifier asc, id asc`.
- The exploratory API tier has a low, undocumented rate limit with no `Retry-After` header on
  429s, so the client throttles proactively (`min_request_interval` in `config.toml`) and retries
  failed requests with exponential backoff.
