---
title: Rules
sql:
  findings: ./loaders/findings.parquet
  activities: ./loaders/activities.json
---

```js
import {sectionName, severityColor, fmtNumber} from "./components/format.js";
```

```js
const rulesDoc = FileAttachment("loaders/rules.json").json();
```

# Rule explorer

```js
const ruleCodes = rulesDoc.rules.map((r) => r.code);
const rulesByCodeMap = new Map(rulesDoc.rules.map((r) => [r.code, r]));
const requestedCode = new URLSearchParams(location.search).get("code");
const defaultCode = ruleCodes.includes(requestedCode) ? requestedCode : ruleCodes[0];
```

```js
const selectedCode = view(
  Inputs.select(ruleCodes, {
    value: defaultCode,
    label: "Rule",
    format: (d) => `${d} — ${rulesByCodeMap.get(d).title}`,
  })
);
```

```js
const rule = rulesByCodeMap.get(selectedCode);
```

<div class="card">
  <h2>${rule.code} <span style="color: ${severityColor(rule.severity)}">${rule.severity}</span></h2>
  <h3>${rule.title}</h3>
  <p>${rule.description || "No further description."}</p>
  <p class="muted">Section ${rule.section} — ${sectionName(rule.section)} ${rule.systemic ? "· flagged as a systemic publisher pattern" : ""} ${rule.enabled ? "" : "· disabled in rules.toml"}</p>
</div>

```js
const ruleCounts = await sql`
  SELECT count(*) AS findings, count(DISTINCT iati_identifier) AS activities
  FROM findings WHERE code = ${selectedCode}
`;
```

<div class="grid grid-cols-2">
  <div class="card"><h2>${fmtNumber(ruleCounts[0].findings)}</h2><span>Findings</span></div>
  <div class="card"><h2>${fmtNumber(ruleCounts[0].activities)}</h2><span>Activities affected</span></div>
</div>

## Most affected activities

```js
const topActivities = await sql`
  SELECT a.identifier, a.title, a.url_d_portal, count(*) AS findings
  FROM findings f JOIN activities a ON a.identifier = f.iati_identifier
  WHERE f.code = ${selectedCode}
  GROUP BY a.identifier, a.title, a.url_d_portal
  ORDER BY findings DESC
  LIMIT 10
`;
```

```js
Inputs.table([...topActivities], {
  columns: ["identifier", "title", "findings", "url_d_portal"],
  header: {identifier: "Activity", title: "Title", findings: "Findings", url_d_portal: "d-portal"},
  format: {url_d_portal: (u) => html`<a href=${u} target="_blank" rel="noopener">Open ↗</a>`},
  width: {title: 320},
})
```

## Findings for this rule

```js
const findingRows = await sql`
  SELECT f.iati_identifier, f.message, f.systemic, a.title AS activity_title, a.url_d_portal
  FROM findings f JOIN activities a ON a.identifier = f.iati_identifier
  WHERE f.code = ${selectedCode}
  ORDER BY f.iati_identifier
  LIMIT 500
`;
```

Showing up to 500 of ${fmtNumber(ruleCounts[0].findings)} findings.

```js
Inputs.table([...findingRows], {
  columns: ["iati_identifier", "activity_title", "message", "systemic", "url_d_portal"],
  header: {
    iati_identifier: "Activity",
    activity_title: "Title",
    message: "Finding",
    systemic: "Systemic",
    url_d_portal: "d-portal",
  },
  format: {
    systemic: (d) => (d ? "yes" : ""),
    url_d_portal: (u) => html`<a href=${u} target="_blank" rel="noopener">Open ↗</a>`,
  },
  width: {message: 420, activity_title: 260},
  rows: 15,
})
```
