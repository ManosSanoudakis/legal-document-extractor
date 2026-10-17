// Read and update deed values by path, e.g. "property.kaek" or "sellers[0].tax_id".
import type { Deed } from "./types";

type Node = Record<string, unknown>;

function parse(path: string): [section: string, index: number | null, key: string] {
  const m = path.match(/^(\w+)(?:\[(\d+)\])?\.(\w+)$/);
  if (!m) throw new Error(`Bad field path: ${path}`);
  return [m[1], m[2] === undefined ? null : Number(m[2]), m[3]];
}

export function getPath(deed: Deed, path: string): unknown {
  const [section, index, key] = parse(path);
  const node = (deed as Node)[section];
  const item = index === null ? node : Array.isArray(node) ? node[index] : undefined;
  return item && typeof item === "object" ? (item as Node)[key] : undefined;
}

/** Return a copy of the deed with one value replaced. */
export function setPath(deed: Deed, path: string, value: unknown): Deed {
  const [section, index, key] = parse(path);
  const node = (deed as Node)[section];
  if (index === null) {
    return { ...deed, [section]: { ...((node as Node) ?? {}), [key]: value } };
  }
  const list = Array.isArray(node) ? [...node] : [];
  list[index] = { ...(list[index] as Node), [key]: value };
  return { ...deed, [section]: list };
}

/** Like getPath, but undefined for a path that is not a single field (e.g. "sellers"). */
export function tryGetPath(deed: Deed, path: string): unknown {
  try {
    return getPath(deed, path);
  } catch {
    return undefined;
  }
}

/** Fields stored as numbers; everything else is text. */
export function isNumberField(path: string): boolean {
  return path.endsWith(".area_sqm") || path.endsWith(".price");
}

/** "185.000,50" or "185000.5" → number; empty → null; anything else stays text (and fails validation). */
export function parseNumber(input: string): number | string | null {
  const s = input.trim();
  if (!s) return null;
  const normalised = s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s;
  const n = Number(normalised.replace(/[^\d.-]/g, ""));
  return Number.isFinite(n) && /\d/.test(s) ? n : s;
}
