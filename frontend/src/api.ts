import type {
  AppConfig,
  Deed,
  DocumentChoice,
  EvaluationReport,
  ExtractionResult,
  HistoryItem,
  HistoryRecord,
  Job,
  JobDocument,
  JobTask,
  RecheckAnswer,
  RecheckResult,
  ValidationIssue,
} from "./types";

export const SAMPLE_URL = "/api/sample";

export function demoPdfUrl(id: string): string {
  return `/api/demo/${encodeURIComponent(id)}/pdf`;
}

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

export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>("/api/config");
}

/** A demo deed's saved result: no API key, no model call. */
export function getDemo(id: string): Promise<ExtractionResult> {
  return request<ExtractionResult>(`/api/demo/${encodeURIComponent(id)}`);
}

/** Start background work on one document or many; returns at once. */
export function createJob(
  docs: DocumentChoice | File[],
  apiKey: string,
  params: { task: JobTask; model?: string; deed?: string; fields?: string },
): Promise<Job> {
  const form = new FormData();
  if (Array.isArray(docs)) docs.forEach((f) => form.append("files", f));
  else if (docs.kind === "sample") form.append("use_sample", "true");
  else if (docs.kind === "demo") form.append("demo", docs.demo.id);
  else form.append("files", docs.file);
  for (const [name, value] of Object.entries(params)) if (value !== undefined) form.append(name, value);
  return request<Job>("/api/jobs", { method: "POST", headers: { "X-Gemini-Key": apiKey }, body: form });
}

export function getJobResult(jobId: string, docId: string): Promise<ExtractionResult> {
  return request<ExtractionResult>(`/api/jobs/${jobId}/documents/${docId}`);
}

/** Run one document as a background job, reporting its stage, and return its result. */
async function runJob<T>(
  doc: DocumentChoice,
  apiKey: string,
  params: Parameters<typeof createJob>[2],
  onStage?: (doc: JobDocument) => void,
): Promise<T> {
  const job = await waitForJob(await createJob(doc, apiKey, params), (j) => onStage?.(j.documents[0]));
  const [result] = job.documents;
  if (result.status === "error") throw new ApiError(result.error ?? "Processing failed", 0);
  return request<T>(`/api/jobs/${job.id}/documents/${result.id}`);
}

export function extract(
  doc: DocumentChoice,
  model: string,
  apiKey: string,
  onStage?: (doc: JobDocument) => void,
): Promise<ExtractionResult> {
  return runJob<ExtractionResult>(doc, apiKey, { task: "extract", model }, onStage);
}

/** Poll a job about once a second, reporting progress, until every document is done or failed. */
export async function waitForJob(job: Job, onUpdate: (job: Job) => void): Promise<Job> {
  let current = job;
  onUpdate(current);
  while (current.status !== "done") {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    current = await request<Job>(`/api/jobs/${job.id}`);
    onUpdate(current);
  }
  return current;
}

export function listHistory(): Promise<HistoryItem[]> {
  return request<HistoryItem[]>("/api/history");
}

export function getHistory(id: string): Promise<HistoryRecord> {
  return request<HistoryRecord>(`/api/history/${id}`);
}

/** Save the user's corrections (null = none, the model's answer stands) and the fields they checked. */
export function saveHistory(id: string, edited: Deed | null, reviewed: string[]): Promise<unknown> {
  return request(`/api/history/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edited, reviewed }),
  });
}

export async function deleteHistory(id: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/history/${id}`, { method: "DELETE" });
  } catch {
    throw new ApiError("Cannot reach the API server. Is the backend running?", 0);
  }
  if (!res.ok && res.status !== 404) throw new ApiError(`Delete failed (${res.status})`, res.status);
}

/** Every model on one document, compared (and scored, for the sample and demo deeds). */
export function evaluate(doc: DocumentChoice, apiKey: string): Promise<EvaluationReport> {
  return runJob<EvaluationReport>(doc, apiKey, { task: "evaluate" });
}

/** Read a few flagged fields again at higher resolution (one model call). */
export async function recheck(
  doc: DocumentChoice,
  model: string,
  apiKey: string,
  deed: Deed,
  fields: string[],
): Promise<RecheckAnswer[]> {
  const params = { task: "recheck" as const, model, deed: JSON.stringify(deed), fields: JSON.stringify(fields) };
  return (await runJob<RecheckResult>(doc, apiKey, params)).answers;
}

/** Re-run the backend checks on a deed the user has edited. */
export async function validate(deed: Deed): Promise<ValidationIssue[]> {
  const body = await request<{ issues: ValidationIssue[] }>("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(deed),
  });
  return body.issues;
}

async function download(path: string, body: unknown, filename: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Cannot reach the API server. Is the backend running?", 0);
  }
  if (!res.ok) throw new ApiError(`Export failed (${res.status})`, res.status);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

/** Download the deed as an Excel or CSV file. */
export function exportDeed(deed: Deed, format: "xlsx" | "csv"): Promise<void> {
  return download(`/api/export?format=${format}`, deed, `extracted_deed.${format}`);
}

/** Download many deeds as one file: one row per deed. */
export function exportBatch(deeds: { name: string; deed: Deed }[], format: "xlsx" | "csv"): Promise<void> {
  return download(`/api/export/batch?format=${format}`, { deeds }, `deeds.${format}`);
}
