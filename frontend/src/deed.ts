// Read and update deed values by path, e.g. "property.kaek" or "sellers[0].tax_id".
import type { ExtractionResult } from "./types";

type Node = Record<string, unknown>;

function parse(path: string): [section: string, index: number | null, key: string] {
  const m = path.match(/^(\w+)(?:\[(\d+)\])?\.(\w+)$/);
  if (!m) throw new Error(`Bad field path: ${path}`);
  return [m[1], m[2] === undefined ? null : Number(m[2]), m[3]];
}

export function getPath(deed: ExtractionResult, path: string): unknown {
  const [section, index, key] = parse(path);
  const node = (deed as Node)[section];
  const item = index === null ? node : Array.isArray(node) ? node[index] : undefined;
  return item && typeof item === "object" ? (item as Node)[key] : undefined;
}

/** Return a copy of the deed with one value replaced. */
export function setPath(deed: ExtractionResult, path: string, value: unknown): ExtractionResult {
  const [section, index, key] = parse(path);
  const node = (deed as Node)[section];
  if (index === null) {
    return { ...deed, [section]: { ...((node as Node) ?? {}), [key]: value } };
  }
  const list = Array.isArray(node) ? [...node] : [];
  list[index] = { ...(list[index] as Node), [key]: value };
  return { ...deed, [section]: list };
}

/** The deed without the response metadata, as sent to /api/validate and /api/export. */
export function deedData(deed: ExtractionResult): ExtractionResult {
  const { _meta, _validation, _error, ...data } = deed;
  return data;
}
