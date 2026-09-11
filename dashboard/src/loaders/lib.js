// Shared helper for the JS data loaders in this directory. Not a loader itself.
//
// The dashboard's only contact with the Python side is the file tree written by
// `iati_scout.quality.export.write_export()` under `data/quality/<org>/export/` at
// the repo root — never `iati_scout` itself. This module just locates that folder.
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// here = dashboard/src/loaders -> dashboard root is two levels up, repo root one more.
const dashboardRoot = path.resolve(here, "..", "..");
const repoRoot = path.resolve(dashboardRoot, "..");

export function resolveExportDir() {
  const explicit = process.env.IATI_SCOUT_EXPORT_DIR;
  if (explicit) {
    const dir = path.resolve(repoRoot, explicit);
    if (!existsSync(dir)) {
      throw new Error(`IATI_SCOUT_EXPORT_DIR does not exist: ${dir}`);
    }
    return dir;
  }

  const qualityDir = path.resolve(repoRoot, "data", "quality");
  const org = process.env.IATI_SCOUT_ORG_ID || process.env.IATI_ORG_ID;
  if (org) {
    const dir = path.join(qualityDir, org, "export");
    if (!existsSync(dir)) {
      throw new Error(
        `No export found at ${dir}. Run \`iati-scout check --org-id ${org}\` first.`
      );
    }
    return dir;
  }

  if (!existsSync(qualityDir)) {
    throw new Error(
      `No data/quality directory found at ${qualityDir}. Run \`iati-scout check --org-id <ORG>\` ` +
        `first, or set IATI_SCOUT_EXPORT_DIR to point at an export/ folder directly.`
    );
  }
  const candidates = readdirSync(qualityDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => path.join(qualityDir, d.name, "export"))
    .filter((dir) => existsSync(dir));

  if (candidates.length === 1) return candidates[0];
  if (candidates.length === 0) {
    throw new Error(
      `No exports found under ${qualityDir}. Run \`iati-scout check --org-id <ORG>\` first.`
    );
  }
  throw new Error(
    `Multiple exports found under ${qualityDir}:\n  ${candidates.join("\n  ")}\n` +
      `Set IATI_SCOUT_ORG_ID (or IATI_SCOUT_EXPORT_DIR) to pick one.`
  );
}

export function exportFile(name) {
  return path.join(resolveExportDir(), name);
}
