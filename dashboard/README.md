# IATI Scout dashboard

An [Observable Framework](https://observablehq.com/framework/) static site that visualises the
data-quality findings produced by the Python tool in this repo. This is a **separate layer**: the
dashboard never imports `iati_scout` and has no Python dependency at runtime — it only reads the
files under `data/quality/<org_id>/export/`, written by `iati-scout check`
(see [`../src/iati_scout/quality/export.py`](../src/iati_scout/quality/export.py)).

## The contract

```
data/quality/<org_id>/export/
├── meta.json         # run metadata: org, timestamps, tool version, activity count
├── rules.json        # rule catalogue: scout rules + every validator rule id seen, with source
├── summary.json       # pre-aggregated counts (totals, per rule/section/severity/category/source)
├── activities.json    # one row per activity: identity, key dates, per-severity + per-source counts
└── findings.parquet   # one row per finding, for DuckDB-WASM
```

By default the dashboard looks for exactly one `data/quality/*/export/` directory at the repo
root and uses it. If you have exports for more than one organisation, or keep them elsewhere, set
one of these environment variables before running `npm run dev` / `npm run build`:

- `IATI_SCOUT_ORG_ID` — picks `data/quality/<org>/export/`
- `IATI_SCOUT_EXPORT_DIR` — points directly at an `export/` folder (relative to the repo root, or
  absolute)

## Run it

Requires Node.js ≥ 18 and at least one export produced by `iati-scout check` (see the repo root
[README](../README.md#data-quality-checks)).

```
npm install
npm run dev      # http://localhost:3000, live-reloads on file changes
npm run build    # writes a fully static site to dist/
```

`npm run build` needs no Python, no API key, and no network access beyond the CDN-hosted DuckDB-WASM
bundle Framework fetches at build time — the resulting `dist/` folder can be hosted anywhere static
files are served (GitHub Pages, DigitalOcean, ...).

## Pages

- **Overview** — org header, validity + per-severity KPIs, documents validated, findings-per-category chart, rule catalogue
- **Rules** — pick a rule (or arrive via `rules?code=E-A01`), see its counts, most-affected
  activities, and up to 500 sample findings
- **Findings** — filter by source/severity/category/rule/systemic and free text, browse up to 1 000 matches
- **Activities** — search activities by id/title, see one activity's dates, links, and findings

Systemic findings (publisher-wide patterns rather than per-activity issues — see the rules.toml
`systemic` flag in the root README) are hidden by default on every page and can be switched on.
