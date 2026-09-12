---
title: Activities
sql:
  findings: ./loaders/findings.parquet
  activities: ./loaders/activities.json
---

```js
import {fmtDate, dPortalUrl} from "./components/format.js";
```

# Activity explorer

```js
const activities = [...(await sql`SELECT * FROM activities ORDER BY identifier`)];
```

```js
const search = view(Inputs.search(activities, {placeholder: "Search by activity id or title…"}));
```

```js
const selection = view(
  Inputs.table(search, {
    columns: ["identifier", "title", "status", "errors", "warnings"],
    header: {identifier: "Activity", title: "Title", status: "Status", errors: "Errors", warnings: "Warnings"},
    multiple: false,
    rows: 12,
    width: {title: 340},
  })
);
```

---

```js
selection
  ? html`<div class="card">
      <h2>${selection.title}</h2>
      <p class="muted">${selection.identifier} · status ${selection.status} · hierarchy ${selection.hierarchy ?? "–"}</p>
      <p>
        Planned: ${fmtDate(selection.planned_start)} → ${fmtDate(selection.planned_end)}<br>
        Actual: ${fmtDate(selection.actual_start)} → ${fmtDate(selection.actual_end)}<br>
        Last updated: ${fmtDate(selection.last_updated)}
      </p>
      <p>
        ${selection.parent_id ? html`Parent: <a href=${dPortalUrl(selection.parent_id)} target="_blank" rel="noopener">${selection.parent_id} ↗</a><br>` : ""}
        <a href=${selection.url_d_portal} target="_blank" rel="noopener">Open on d-portal ↗</a>
      </p>
    </div>`
  : html`<p class="muted">Select an activity above to see its findings.</p>`
```

```js
const activityFindings = selection
  ? [...(await sql`
      SELECT code, severity, systemic, message
      FROM findings
      WHERE iati_identifier = ${selection.identifier}
      ORDER BY severity, code
    `)]
  : [];
```

```js
selection
  ? Inputs.table(activityFindings, {
      columns: ["code", "severity", "message", "systemic"],
      header: {code: "Code", severity: "Severity", message: "Finding", systemic: "Systemic"},
      format: {
        code: (d) => html`<a href="rules?code=${d}">${d}</a>`,
        systemic: (d) => (d ? "yes" : ""),
      },
      width: {message: 480},
      rows: 15,
    })
  : ""
```
