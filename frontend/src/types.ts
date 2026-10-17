// Mirrors the JSON returned by the FastAPI backend (see schema.py).

export interface Party {
  full_name?: string | null;
  tax_id?: string | null;
  id_document?: string | null;
  address?: string | null;
}

export interface Representative {
  full_name?: string | null;
  represents?: string | null;
  tax_id?: string | null;
  id_document?: string | null;
}

/** The deed's data, in the shape of schema.Deed. */
export interface Deed {
  notary?: { name?: string | null; location?: string | null; registry_number?: string | null } | null;
  sellers?: Party[] | null;
  buyers?: Party[] | null;
  legal_representatives?: Representative[] | null;
  property?: {
    type?: string | null;
    address?: string | null;
    municipal_unit?: string | null;
    floor?: string | null;
    area_sqm?: number | string | null;
    kaek?: string | null;
    building_permit?: string | null;
  } | null;
  transaction?: { deed_type?: string | null; price?: number | string | null; date?: string | null } | null;
  sources?: Source[] | null;
}

/** One extraction (schema.ExtractionResult): the deed, how it was made, and what failed the checks. */
export interface ExtractionResult {
  deed: Deed;
  meta: {
    model: string;
    provider: string;
    pages: number;
    /** Every page had text, so the values were checked against it */
    text_layer: boolean;
    elapsed_seconds: number;
    /** Set when the result is in history, so edits can be saved there */
    history_id?: string | null;
    /** e.g. where a demo result came from */
    note?: string | null;
  };
  validation: ValidationIssue[];
  /** The model's answer could not be parsed */
  error?: string | null;
}

/** Where the model found a value: page number and the exact text it read. */
export interface Source {
  field: string;
  page: number | null;
  quote: string | null;
}

/** A second, independent reading of one flagged field (see extractor.run_recheck). */
export interface RecheckAnswer {
  field: string;
  value: string | null;
  page: number | null;
  quote: string | null;
  agrees: boolean;
  /** null when the PDF has no text layer to look in */
  found_in_text: boolean | null;
}

export interface RecheckResult {
  answers: RecheckAnswer[];
  model: string;
  pages: number[];
  elapsed_seconds: number;
}

/** A sanity check that failed (see validators.py). */
export interface ValidationIssue {
  field: string;
  value: unknown;
  message: string;
  severity: "error" | "warning";
}

export interface Accuracy {
  accuracy_pct: number;
  correct: number;
  total: number;
  extra_parties: number;
  mismatches: { field: string; expected: unknown; got: unknown }[];
}

export interface Completeness {
  scalar_pct: number;
  list_pct: number;
  overall_pct: number;
  filled: number;
  total: number;
}

export interface ModelRun {
  model: string;
  elapsed_s: number;
  /** null if the run failed */
  completeness: Completeness | null;
  accuracy?: Accuracy | null;
  checks_failed?: number;
  error: string | null;
}

export interface EvaluationReport {
  pdf: string;
  models: ModelRun[];
  field_diffs?: { field: string; model_a: unknown; model_b: unknown }[];
  winner?: { accuracy: string; basis?: "accuracy" | "completeness"; tie?: boolean; speed: string };
  raw_results: Record<string, ExtractionResult | null>;
}

/** A fictional deed with a saved model answer, shown without an API key (see demo.py). */
export interface DemoDeed {
  id: string;
  title: string;
  description: string;
}

export interface AppConfig {
  models: string[];
  sample_available: boolean;
  demos: DemoDeed[];
  max_file_mb: number;
  max_pages: number;
  max_batch_files: number;
}

/** A document's progress in a background job (see jobs.py). */
export type JobStage = "queued" | "reading" | "extracting" | "done" | "error";

export interface JobDocument {
  id: string;
  filename: string;
  status: JobStage;
  error: string | null;
  elapsed_seconds: number | null;
  summary: { deed_type: string | null; price: number | null; date: string | null; flags: number; errors: number } | null;
}

/** A saved result, as listed in the History tab (see history.py). */
export interface HistoryItem {
  id: string;
  filename: string;
  model: string;
  created: number;
  updated: number;
  edited: boolean;
  summary: NonNullable<JobDocument["summary"]> & { to_check: number };
}

export interface HistoryRecord {
  id: string;
  filename: string;
  model: string;
  created: number;
  updated: number;
  result: ExtractionResult;
  edited: Deed | null;
  reviewed: string[];
}

export type JobTask = "extract" | "evaluate" | "recheck";

export interface Job {
  id: string;
  kind: JobTask;
  model: string | null;
  status: "running" | "done";
  documents: JobDocument[];
}

/** The document the user picked: a demo deed, the bundled sample or an uploaded file. */
export type DocumentChoice = { kind: "demo"; demo: DemoDeed } | { kind: "sample" } | { kind: "upload"; file: File };
