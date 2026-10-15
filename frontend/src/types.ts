// Mirrors the JSON returned by the FastAPI backend (see extractor.SCHEMA).

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

export interface ExtractionResult {
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
  _meta?: { model: string; provider: string; pages: number; elapsed_seconds: number };
  _error?: string;
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
  completeness: Completeness | Record<string, never>;
  error: string | null;
}

export interface EvaluationReport {
  pdf: string;
  models: ModelRun[];
  field_diffs?: { field: string; model_a: unknown; model_b: unknown }[];
  winner?: { accuracy: string; speed: string };
  raw_results: Record<string, ExtractionResult>;
}

export interface AppConfig {
  models: string[];
  sample_available: boolean;
  max_file_mb: number;
  max_pages: number;
}

/** The document the user picked: the bundled sample or an uploaded file. */
export type DocumentChoice = { kind: "sample" } | { kind: "upload"; file: File };
