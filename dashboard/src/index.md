---
title: Overview
sql:
  findings: ./loaders/findings.parquet
---

```js
import {sectionName, severityColor, fmtNumber, fmtPercent, fmtDate, rulesByCode} from "./components/format.js";
```

```js
const meta = FileAttachment("loaders/meta.json").json();
const summary = FileAttachment("loaders/summary.json").json();
const rulesDoc = FileAttachment("loaders/rules.json").json();
```

# ${meta.org_name ?? meta.org_id}

<span class="muted">${meta.org_id} · checked ${fmtDate(meta.checked_at)} · data fetched ${fmtDate(meta.fetched_at)} · ${fmtNumber(meta.activity_count)} activities</span>

```js
const showSystemic = view(Inputs.toggle({label: "Include systemic findings", value: false}));
```

<div class="grid grid-cols-4">
  <div class="card"><h2>${fmtNumber(summary.totals.errors)}</h2><span>Errors</span></div>
  <div class="card"><h2>${fmtNumber(summary.totals.warnings)}</h2><span>Warnings</span></div>
  <div class="card"><h2>${fmtPercent(summary.totals.activities_affected / summary.totals.activities)}</h2><span>Activities with a finding</span></div>
  <div class="card"><h2>${fmtPercent(summary.totals.systemic_findings / summary.totals.findings)}</h2><span>Systemic findings</span></div>
</div>

## Findings by rule section

```js
const ruleRows = rulesDoc.rules.map((r) => ({
  ...r,
  findings: summary.per_rule[r.code]?.findings ?? 0,
  activities: summary.per_rule[r.code]?.activities ?? 0,
}));
const visibleRuleRows = ruleRows.filter((r) => showSystemic || !r.systemic);
```

```js
const bySection = d3.rollups(
  visibleRuleRows,
  (v) => d3.sum(v, (d) => d.findings),
  (d) => d.section,
  (d) => d.severity
).flatMap(([section, sevs]) => sevs.map(([severity, findings]) => ({section, severity, findings})));
```

```js
Plot.plot({
  marginLeft: 40,
  width: 800,
  x: {label: "Findings", grid: true},
  y: {label: null, domain: ["A", "B", "C", "D", "E", "F", "G"]},
  color: {domain: ["error", "warning"], range: [severityColor("error"), severityColor("warning")], legend: true},
  marks: [
    Plot.barX(bySection, {y: "section", x: "findings", fill: "severity", tip: true}),
    Plot.ruleX([0]),
  ],
})
```

## Rule catalogue

```js
Inputs.table(visibleRuleRows, {
  columns: ["code", "severity", "title", "section", "findings", "activities", "systemic"],
  header: {
    code: "Code",
    severity: "Severity",
    title: "Rule",
    section: "Section",
    findings: "Findings",
    activities: "Activities",
    systemic: "Systemic",
  },
  format: {
    code: (d) => html`<a href="rules?code=${d}">${d}</a>`,
    section: (d) => sectionName(d),
    systemic: (d) => (d ? "yes" : ""),
  },
  sort: "findings",
  reverse: true,
  rows: 20,
  width: {title: 340},
})
```
