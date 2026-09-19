---
title: Overview
sql:
  findings: ./loaders/findings.parquet
---

```js
import {categoryName, sourceName, severityColor, SEVERITY_ORDER, fmtNumber, fmtPercent, fmtDate} from "./components/format.js";
```

```js
const meta = FileAttachment("loaders/meta.json").json();
const summary = FileAttachment("loaders/summary.json").json();
const rulesDoc = FileAttachment("loaders/rules.json").json();
```

# ${meta.org_name ?? meta.org_id}

<span class="muted">${meta.org_id} · checked ${fmtDate(meta.checked_at)} · data fetched ${fmtDate(meta.fetched_at)} · ${fmtNumber(meta.activity_count)} activities</span>

Findings come from two sources. Violations of the **IATI standard** are taken
from the official [IATI Validator](https://validator.iatistandard.org/) and keep
its severity (`critical`/`error`/`warning`). Everything iati-scout adds on top
is reported as `advisory`, because a heuristic is not a standard violation —
filter on **source**, not severity, to separate them.

```js
const v = meta.validator ?? {};
```

<div class="grid grid-cols-4">
  <div class="card"><h2>${v.valid == null ? "–" : (v.valid ? "Valid" : "Invalid")}</h2><span>Against IATI ${v.iati_version ?? ""}</span></div>
  <div class="card"><h2>${fmtNumber((summary.totals.critical ?? 0) + (summary.totals.error ?? 0))}</h2><span>Standard errors</span></div>
  <div class="card"><h2>${fmtNumber(summary.totals.warning ?? 0)}</h2><span>Standard warnings</span></div>
  <div class="card"><h2>${fmtNumber(summary.totals.advisory ?? 0)}</h2><span>Advisories</span></div>
</div>

<div class="grid grid-cols-3">
  <div class="card"><h2>${fmtPercent(summary.totals.activities_affected / summary.totals.activities)}</h2><span>Activities with a finding</span></div>
  <div class="card"><h2>${fmtPercent(summary.totals.systemic_findings / summary.totals.findings)}</h2><span>Systemic findings</span></div>
  <div class="card"><h2>${fmtNumber(v.documents?.length ?? 0)}</h2><span>Documents validated</span></div>
</div>

## Documents

```js
Inputs.table(v.documents ?? [], {
  columns: ["registry_name", "valid", "document_url"],
  header: {registry_name: "Registry dataset", valid: "Valid", document_url: "Published file"},
  format: {
    valid: (d) => (d ? "yes" : "NO"),
    document_url: (d) => html`<a href=${d} target="_blank">${d}</a>`,
  },
  width: {document_url: 420},
})
```

## Findings by category

```js
const showSystemic = view(Inputs.toggle({label: "Include systemic findings", value: false}));
```

```js
const ruleRows = rulesDoc.rules.map((r) => ({
  ...r,
  findings: summary.per_rule[r.code]?.findings ?? 0,
  activities: summary.per_rule[r.code]?.activities ?? 0,
}));
const visibleRuleRows = ruleRows.filter((r) => showSystemic || !r.systemic);
```

```js
const byCategory = d3.rollups(
  visibleRuleRows,
  (v) => d3.sum(v, (d) => d.findings),
  (d) => d.category,
  (d) => d.severity
).flatMap(([category, sevs]) => sevs.map(([severity, findings]) => ({category, severity, findings})));
const categoryDomain = d3.rollups(byCategory, (v) => d3.sum(v, (d) => d.findings), (d) => d.category)
  .sort((a, b) => d3.descending(a[1], b[1]))
  .map(([c]) => c);
```

```js
Plot.plot({
  marginLeft: 170,
  width: 800,
  x: {label: "Findings", grid: true},
  y: {label: null, domain: categoryDomain, tickFormat: categoryName},
  color: {
    domain: SEVERITY_ORDER,
    range: SEVERITY_ORDER.map(severityColor),
    legend: true,
  },
  marks: [
    Plot.barX(byCategory, {y: "category", x: "findings", fill: "severity", tip: true}),
    Plot.ruleX([0]),
  ],
})
```

## Rule catalogue

```js
Inputs.table(visibleRuleRows, {
  columns: ["code", "source", "severity", "title", "category", "findings", "activities", "systemic"],
  header: {
    code: "Rule",
    source: "Source",
    severity: "Severity",
    title: "Description",
    category: "Category",
    findings: "Findings",
    activities: "Activities",
    systemic: "Systemic",
  },
  format: {
    code: (d) => html`<a href="rules?code=${d}">${d}</a>`,
    source: (d) => sourceName(d),
    category: (d) => categoryName(d),
    systemic: (d) => (d ? "yes" : ""),
  },
  sort: "findings",
  reverse: true,
  rows: 20,
  width: {title: 340},
})
```
