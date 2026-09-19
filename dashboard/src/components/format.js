// Small formatting/lookup helpers shared across pages. Deliberately dependency-free
// (no "npm:" imports) so it can be imported from any page without extra build cost.

// The IATI Validator's four-level severity scale. `advisory` covers both the
// validator's own 1000.x checks and every iati-scout rule, so use `source` —
// not severity — to tell the two apart.
export const SEVERITY_COLOR = {
  critical: "#8b1a1a",
  error: "#d64545",
  warning: "#dba13b",
  advisory: "#4a8fc4",
};

export const SEVERITY_ORDER = ["critical", "error", "warning", "advisory"];

export const SOURCE_NAME = {
  validator: "Official IATI validator",
  scout: "iati-scout",
};

// The official category vocabulary, from the IATI ruleset's `ruleInfo.category`.
export const CATEGORY_NAME = {
  iati: "Activity dates & status",
  financial: "Financial",
  classifications: "Classification",
  relations: "Hierarchy & relations",
  identifiers: "Identifiers",
  participating: "Participating organisations",
  organisation: "Organisation",
  geo: "Geography",
  information: "Information",
  performance: "Results & performance",
};

export const SECTION_NAME = {
  A: "Activity dates & status",
  B: "Financial consistency",
  C: "Classification",
  D: "Hierarchy & relations",
  E: "Organisations",
  F: "Text & locations",
  G: "Results",
};

export function sectionName(section) {
  return SECTION_NAME[section] ?? section;
}

export function categoryName(category) {
  return CATEGORY_NAME[category] ?? category;
}

export function sourceName(source) {
  return SOURCE_NAME[source] ?? source;
}

export function severityColor(severity) {
  return SEVERITY_COLOR[severity] ?? "#888";
}

export function fmtNumber(n) {
  return n == null ? "–" : n.toLocaleString("en-US");
}

export function fmtPercent(fraction) {
  return fraction == null ? "–" : `${(fraction * 100).toFixed(0)}%`;
}

export function fmtDate(value) {
  // Plain JSON-sourced dates arrive as ISO strings; the same field read back through a
  // DuckDB query (activities.json registered as a SQL table) comes back as a JS Date,
  // since DuckDB auto-detects and types date-like strings on ingest.
  if (!value) return "–";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).slice(0, 10);
}

// Mirrors `d_portal_activity_url` in iati_scout/quality/findings.py.
export function dPortalUrl(identifier) {
  const encoded = encodeURIComponent(identifier).replace(/%3A/g, ":");
  return `https://d-portal.iatistandard.org/ctrack.html#view=act&aid=${encoded}`;
}

// Builds `code -> rule metadata` from the rules.json export (`{thresholds, rules: [...]}`).
export function rulesByCode(rulesDoc) {
  return new Map(rulesDoc.rules.map((r) => [r.code, r]));
}

// Builds `identifier -> activity row` from the activities.json export.
export function activitiesByIdentifier(activities) {
  return new Map(activities.map((a) => [a.identifier, a]));
}
