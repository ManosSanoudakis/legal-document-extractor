import type {
  AppConfig,
  DocumentChoice,
  EvaluationReport,
  ExtractionResult,
  RecheckAnswer,
  ValidationIssue,
} from "./types";

export const SAMPLE_URL = "/api/sample";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the API server. Is the backend running?", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(detail || `Request failed (${res.status})`, res.status);
  }
  return res.json() as Promise<T>;
}

function documentForm(doc: DocumentChoice): FormData {
  const form = new FormData();
  if (doc.kind === "sample") form.append("use_sample", "true");
  else form.append("file", doc.file);
  return form;
}

export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>("/api/config");
}

export function extract(doc: DocumentChoice, model: string, apiKey: string): Promise<ExtractionResult> {
  const form = documentForm(doc);
  form.append("model", model);
  return request<ExtractionResult>("/api/extract", {
    method: "POST",
    headers: { "X-Gemini-Key": apiKey },
    body: form,
  });
}

export function evaluate(doc: DocumentChoice, apiKey: string): Promise<EvaluationReport> {
  return request<EvaluationReport>("/api/evaluate", {
    method: "POST",
    headers: { "X-Gemini-Key": apiKey },
    body: documentForm(doc),
  });
}

/** Read a few flagged fields again at higher resolution (one model call). */
export async function recheck(
  doc: DocumentChoice,
  model: string,
  apiKey: string,
  deed: ExtractionResult,
  fields: string[],
): Promise<RecheckAnswer[]> {
  const form = documentForm(doc);
  form.append("model", model);
  form.append("deed", JSON.stringify(deed));
  form.append("fields", JSON.stringify(fields));
  const body = await request<{ answers: RecheckAnswer[] }>("/api/recheck", {
    method: "POST",
    headers: { "X-Gemini-Key": apiKey },
    body: form,
  });
  return body.answers;
}

/** Re-run the backend checks on a deed the user has edited. */
export async function validate(deed: ExtractionResult): Promise<ValidationIssue[]> {
  const body = await request<{ issues: ValidationIssue[] }>("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(deed),
  });
  return body.issues;
}

/** Download the deed as an Excel or CSV file. */
export async function exportDeed(deed: ExtractionResult, format: "xlsx" | "csv"): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/export?format=${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(deed),
    });
  } catch {
    throw new ApiError("Cannot reach the API server. Is the backend running?", 0);
  }
  if (!res.ok) throw new ApiError(`Export failed (${res.status})`, res.status);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: `extracted_deed.${format}` });
  a.click();
  URL.revokeObjectURL(url);
}
