---
title: Findings
sql:
  findings: ./loaders/findings.parquet
  activities: ./loaders/activities.json
---

```js
import {categoryName, sourceName, SEVERITY_ORDER, fmtNumber} from "./components/format.js";
```

```js
const rulesDoc = FileAttachment("loaders/rules.json").json();
const summary = FileAttachment("loaders/summary.json").json();
```

```js
const rulesByCodeMap = new Map(rulesDoc.rules.map((r) => [r.code, r]));
const categories = Object.keys(summary.per_category ?? {}).sort();
```

# Findings explorer

```js
const source = view(
  Inputs.select(["all", "validator", "scout"], {
    label: "Source",
    value: "all",
    format: (d) => (d === "all" ? "Both sources" : sourceName(d)),
  })
);
```

```js
const severity = view(
  Inputs.select(["all", ...SEVERITY_ORDER], {label: "Severity", value: "all"})
);
```

```js
const category = view(
  Inputs.select(["all", ...categories], {
    label: "Category",
    value: "all",
    format: (d) => (d === "all" ? "All categories" : categoryName(d)),
  })
);
```

```js
const ruleCode = view(
  Inputs.select(["all", ...rulesDoc.rules.map((r) => r.code)], {
    label: "Rule",
    value: "all",
    format: (d) => (d === "all" ? "All rules" : `${d} — ${rulesByCodeMap.get(d)?.title ?? ""}`),
  })
);
```

```js
const includeSystemic = view(Inputs.toggle({label: "Include systemic findings", value: false}));
```

```js
const q = view(Inputs.text({label: "Search", placeholder: "activity id or text in the finding…"}));
```

```js
const qTrimmed = q.trim();
const qLike = `%${qTrimmed}%`;
```

Filters below are combined with AND; each is skipped when left at its "all" / empty default.
`advisory` covers both iati-scout's rules and the validator's own 1000.x checks,
so use **Source** to separate them.

```js
const total = [...(await sql`
  SELECT count(*) AS n
  FROM findings
  WHERE (${source} = 'all' OR source = ${source})
    AND (${severity} = 'all' OR severity = ${severity})
    AND (${category} = 'all' OR category = ${category})
    AND (${ruleCode} = 'all' OR code = ${ruleCode})
    AND (${includeSystemic} OR NOT systemic)
    AND (${qTrimmed} = '' OR message ILIKE ${qLike} OR iati_identifier ILIKE ${qLike})
`)];
```

```js
// LEFT JOIN: the validator reads the published XML, so it can report activities
// the Datastore has not ingested. An inner join would silently drop them.
const rows = await sql`
  SELECT f.code, f.severity, f.category, f.source, f.systemic, f.iati_identifier,
         f.message, f.context, a.title AS activity_title, a.url_d_portal
  FROM findings f LEFT JOIN activities a ON a.identifier = f.iati_identifier
  WHERE (${source} = 'all' OR f.source = ${source})
    AND (${severity} = 'all' OR f.severity = ${severity})
    AND (${category} = 'all' OR f.category = ${category})
    AND (${ruleCode} = 'all' OR f.code = ${ruleCode})
    AND (${includeSystemic} OR NOT f.systemic)
    AND (${qTrimmed} = '' OR f.message ILIKE ${qLike} OR f.iati_identifier ILIKE ${qLike})
  ORDER BY f.code, f.iati_identifier
  LIMIT 1000
`;
```

Showing up to 1 000 of ${fmtNumber(total[0].n)} matching findings.

```js
Inputs.table([...rows], {
  columns: ["code", "source", "severity", "iati_identifier", "activity_title", "message", "context", "systemic", "url_d_portal"],
  header: {
    code: "Rule",
    source: "Source",
    severity: "Severity",
    iati_identifier: "Activity",
    activity_title: "Title",
    message: "Finding",
    context: "Context",
    systemic: "Systemic",
    url_d_portal: "d-portal",
  },
  format: {
    code: (d) => html`<a href="rules?code=${d}">${d}</a>`,
    source: (d) => sourceName(d),
    systemic: (d) => (d ? "yes" : ""),
    url_d_portal: (u) =>
      u ? html`<a href=${u} target="_blank" rel="noopener">Open ↗</a>` : "",
  },
  width: {message: 340, activity_title: 200, context: 260},
  rows: 20,
})
```
