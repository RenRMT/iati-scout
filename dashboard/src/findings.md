---
title: Findings
sql:
  findings: ./loaders/findings.parquet
  activities: ./loaders/activities.json
---

```js
import {sectionName, fmtNumber} from "./components/format.js";
```

```js
const rulesDoc = FileAttachment("loaders/rules.json").json();
const rulesByCodeMap = new Map(rulesDoc.rules.map((r) => [r.code, r]));
```

# Findings explorer

```js
const severity = view(Inputs.select(["all", "error", "warning"], {label: "Severity", value: "all"}));
```

```js
const section = view(
  Inputs.select(["all", "A", "B", "C", "D", "E", "F", "G"], {
    label: "Section",
    value: "all",
    format: (d) => (d === "all" ? "All sections" : `${d} — ${sectionName(d)}`),
  })
);
```

```js
const ruleCode = view(
  Inputs.select(["all", ...rulesDoc.rules.map((r) => r.code)], {
    label: "Rule",
    value: "all",
    format: (d) => (d === "all" ? "All rules" : `${d} — ${rulesByCodeMap.get(d).title}`),
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

```js
const total = await sql`
  SELECT count(*) AS n
  FROM findings
  WHERE (${severity} = 'all' OR severity = ${severity})
    AND (${section} = 'all' OR substr(split_part(code, '-', 2), 1, 1) = ${section})
    AND (${ruleCode} = 'all' OR code = ${ruleCode})
    AND (${includeSystemic} OR NOT systemic)
    AND (${qTrimmed} = '' OR message ILIKE ${qLike} OR iati_identifier ILIKE ${qLike})
`;
```

```js
const rows = await sql`
  SELECT f.code, f.severity, f.systemic, f.iati_identifier, f.message, a.title AS activity_title, a.url_d_portal
  FROM findings f JOIN activities a ON a.identifier = f.iati_identifier
  WHERE (${severity} = 'all' OR f.severity = ${severity})
    AND (${section} = 'all' OR substr(split_part(f.code, '-', 2), 1, 1) = ${section})
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
  columns: ["code", "severity", "iati_identifier", "activity_title", "message", "systemic", "url_d_portal"],
  header: {
    code: "Code",
    severity: "Severity",
    iati_identifier: "Activity",
    activity_title: "Title",
    message: "Finding",
    systemic: "Systemic",
    url_d_portal: "d-portal",
  },
  format: {
    code: (d) => html`<a href="rules?code=${d}">${d}</a>`,
    systemic: (d) => (d ? "yes" : ""),
    url_d_portal: (u) => html`<a href=${u} target="_blank" rel="noopener">Open ↗</a>`,
  },
  width: {message: 380, activity_title: 240},
  rows: 20,
})
```
