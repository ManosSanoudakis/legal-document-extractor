# TODO: SECURITY — run llm-secure-patterns to apply LLM security patterns
#
# This API has no authentication and is meant to run locally. Each caller
# supplies their own Gemini key (X-Gemini-Key header); no key is stored
# server-side. Basic input limits (file size, page count) and an output-token
# cap (extractor.MAX_OUTPUT_TOKENS) are in place.
from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

import fitz
from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from google.genai import errors as genai_errors

from evaluate import run_evaluation
from export import batch_to_csv, batch_to_xlsx, to_csv, to_xlsx
from extractor import MAX_RECHECK_FIELDS, GeminiExtractor, run_pipeline, run_recheck
from jobs import JobLimitError, JobStore
from validators import validate_deed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

SAMPLE_PDF = Path(__file__).parent / "samples" / "sample_deed.pdf"
SAMPLE_TRUTH = SAMPLE_PDF.with_suffix(".json")  # correct answers for the sample
MAX_FILE_MB = 20
MAX_PAGES = 30
MAX_BATCH_FILES = 20

app = FastAPI(
    title="Legal Document Extractor API",
    description="Extract structured data from Greek notarial deeds with Gemini vision.",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_api_key(api_key: str | None) -> str:
    key = (api_key or "").strip()
    if not key:
        raise HTTPException(401, "Missing Gemini API key.")
    if len(key) > 200:
        raise HTTPException(401, "Invalid Gemini API key.")
    return key


def read_document(file: UploadFile | None, use_sample: bool) -> bytes:
    """Return the PDF bytes to process, enforcing size and page limits."""
    if use_sample:
        if not SAMPLE_PDF.exists():
            raise HTTPException(404, "Sample document is not available.")
        return SAMPLE_PDF.read_bytes()

    if file is None:
        raise HTTPException(400, "Upload a PDF or set use_sample=true.")

    max_bytes = MAX_FILE_MB * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"File is larger than {MAX_FILE_MB} MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "File is not a PDF.")

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            pages = pdf.page_count
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "Could not read this PDF.") from None
    if pages > MAX_PAGES:
        raise HTTPException(413, f"PDF has {pages} pages; the limit is {MAX_PAGES}.")
    return data


@contextmanager
def pdf_on_disk(data: bytes) -> Iterator[str]:
    """Write the PDF to a temp file that is always deleted afterwards."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
    try:
        yield tmp.name
    finally:
        if Path(tmp.name).exists():
            os.unlink(tmp.name)


def run_bytes(data: bytes, api_key: str, model: str, on_stage) -> dict:
    """Extract one PDF given as bytes (used by background jobs)."""
    with pdf_on_disk(data) as path:
        return run_pipeline(pdf_path=path, api_key=api_key, model_name=model, on_stage=on_stage)


JOBS = JobStore(run=run_bytes)


def gemini_error(exc: genai_errors.APIError) -> HTTPException:
    """Translate a Gemini API error into a client-facing HTTP error."""
    text = str(exc)
    if exc.code in (401, 403) or "API_KEY_INVALID" in text or "API key not valid" in text:
        return HTTPException(401, "Gemini rejected the API key.")
    if exc.code == 429:
        return HTTPException(429, "Gemini rate limit or quota reached. Try again later.")
    return HTTPException(502, f"Gemini request failed ({exc.code}).")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict:
    return {
        "models": GeminiExtractor.MODELS,
        "sample_available": SAMPLE_PDF.exists(),
        "max_file_mb": MAX_FILE_MB,
        "max_pages": MAX_PAGES,
        "max_batch_files": MAX_BATCH_FILES,
    }


@app.get("/api/sample")
def sample() -> FileResponse:
    if not SAMPLE_PDF.exists():
        raise HTTPException(404, "Sample document is not available.")
    # inline, so the browser shows it in the preview instead of downloading it
    return FileResponse(
        SAMPLE_PDF, media_type="application/pdf",
        filename=SAMPLE_PDF.name, content_disposition_type="inline",
    )


@app.post("/api/extract")
def extract(
    x_gemini_key: Annotated[str | None, Header()] = None,
    model: Annotated[str, Form()] = GeminiExtractor.MODELS[0],
    use_sample: Annotated[bool, Form()] = False,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    api_key = require_api_key(x_gemini_key)
    if model not in GeminiExtractor.MODELS:
        raise HTTPException(400, f"Unknown model '{model}'.")
    data = read_document(file, use_sample)

    logger.info("Extraction started — model=%s sample=%s", model, use_sample)
    try:
        with pdf_on_disk(data) as path:
            return run_pipeline(pdf_path=path, api_key=api_key, model_name=model)
    except genai_errors.APIError as exc:
        logger.warning("Gemini error during extraction: %s", exc.code)
        raise gemini_error(exc) from None


@app.post("/api/jobs", status_code=202)
def create_job(
    x_gemini_key: Annotated[str | None, Header()] = None,
    model: Annotated[str, Form()] = GeminiExtractor.MODELS[0],
    use_sample: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    """Extract one or more PDFs in the background; poll GET /api/jobs/{id} for progress."""
    api_key = require_api_key(x_gemini_key)
    if model not in GeminiExtractor.MODELS:
        raise HTTPException(400, f"Unknown model '{model}'.")
    if use_sample:
        documents = [(SAMPLE_PDF.name, read_document(None, use_sample=True))]
    else:
        if not files:
            raise HTTPException(400, "Upload at least one PDF or set use_sample=true.")
        if len(files) > MAX_BATCH_FILES:
            raise HTTPException(413, f"At most {MAX_BATCH_FILES} files per batch.")
        documents = []
        for f in files:
            try:
                documents.append((f.filename or "upload.pdf", read_document(f, use_sample=False)))
            except HTTPException as exc:
                raise HTTPException(exc.status_code, f"{f.filename}: {exc.detail}") from None

    try:
        job = JOBS.submit(documents, model=model, api_key=api_key)
    except JobLimitError:
        raise HTTPException(429, "Too many jobs are running. Try again in a minute.") from None
    logger.info("Job %s started — model=%s documents=%d", job["id"][:8], model, len(documents))
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = JOBS.snapshot(job_id)
    if job is None:
        raise HTTPException(404, "No such job (finished jobs are kept for an hour).")
    return job


@app.get("/api/jobs/{job_id}/documents/{doc_id}")
def job_result(job_id: str, doc_id: str) -> dict:
    result = JOBS.result(job_id, doc_id)
    if result is None:
        raise HTTPException(404, "No result for this document (yet).")
    return result


@app.post("/api/evaluate")
def evaluate(
    x_gemini_key: Annotated[str | None, Header()] = None,
    use_sample: Annotated[bool, Form()] = False,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    api_key = require_api_key(x_gemini_key)
    data = read_document(file, use_sample)

    logger.info("Evaluation started — sample=%s", use_sample)
    with pdf_on_disk(data) as path:
        # The sample has known answers, so its evaluation can measure real accuracy
        truth = None
        if use_sample and SAMPLE_TRUTH.exists():
            truth = json.loads(SAMPLE_TRUTH.read_text(encoding="utf-8"))
        report = run_evaluation(pdf_path=path, api_key=api_key, truth=truth)
    report["pdf"] = "sample_deed.pdf" if use_sample else (file.filename or "upload.pdf")

    # Per-model failures are caught inside run_evaluation; if every model
    # failed for the same auth reason, surface it as a proper HTTP error.
    errors = [m["error"] for m in report["models"] if m.get("error")]
    all_failed = errors and len(errors) == len(report["models"])
    if all_failed and all("API key" in e or "API_KEY_INVALID" in e for e in errors):
        raise HTTPException(401, "Gemini rejected the API key.")
    return report


@app.post("/api/recheck")
def recheck(
    x_gemini_key: Annotated[str | None, Header()] = None,
    model: Annotated[str, Form()] = GeminiExtractor.MODELS[0],
    deed: Annotated[str, Form()] = "{}",
    fields: Annotated[str, Form()] = "[]",
    use_sample: Annotated[bool, Form()] = False,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Read a few flagged fields again at higher resolution: one model call."""
    api_key = require_api_key(x_gemini_key)
    if model not in GeminiExtractor.MODELS:
        raise HTTPException(400, f"Unknown model '{model}'.")
    try:
        current, wanted = json.loads(deed), json.loads(fields)
    except json.JSONDecodeError:
        raise HTTPException(422, "deed and fields must be JSON.") from None
    if not isinstance(current, dict) or not isinstance(wanted, list) or not all(isinstance(f, str) for f in wanted):
        raise HTTPException(422, "deed must be an object and fields a list of field paths.")
    if not 1 <= len(wanted) <= MAX_RECHECK_FIELDS:
        raise HTTPException(422, f"Re-check between 1 and {MAX_RECHECK_FIELDS} fields.")
    data = read_document(file, use_sample)

    logger.info("Re-check started — model=%s fields=%d", model, len(wanted))
    try:
        with pdf_on_disk(data) as path:
            return run_recheck(pdf_path=path, api_key=api_key, deed=current, fields=wanted, model_name=model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except genai_errors.APIError as exc:
        logger.warning("Gemini error during re-check: %s", exc.code)
        raise gemini_error(exc) from None


# Edited results: the UI re-checks and exports the user's corrected deed.
# These only process the JSON sent in the request; nothing is stored.

def _checked(action, deed: dict):
    try:
        return action(deed)
    except (AttributeError, TypeError, ValueError, KeyError):
        raise HTTPException(422, "The deed data is not in the expected shape.") from None


@app.post("/api/validate")
def validate(deed: Annotated[dict, Body()]) -> dict:
    return {"issues": _checked(validate_deed, deed)}


EXPORTS = {
    "csv": (to_csv, "text/csv; charset=utf-8"),
    "xlsx": (to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


BATCH_EXPORTS = {
    "csv": (batch_to_csv, EXPORTS["csv"][1]),
    "xlsx": (batch_to_xlsx, EXPORTS["xlsx"][1]),
}


@app.post("/api/export/batch")
def export_batch(
    deeds: Annotated[list[dict], Body(embed=True)],
    format: Annotated[Literal["csv", "xlsx"], Query()] = "xlsx",
) -> Response:
    """Many deeds in one file: each item is {"name": <file name>, "deed": <deed>}."""
    def build(items: list[dict]) -> bytes:
        return BATCH_EXPORTS[format][0]([(str(i.get("name") or ""), i["deed"]) for i in items])

    return Response(
        _checked(build, deeds),
        media_type=BATCH_EXPORTS[format][1],
        headers={"Content-Disposition": f'attachment; filename="deeds.{format}"'},
    )


@app.post("/api/export")
def export(
    deed: Annotated[dict, Body()],
    format: Annotated[Literal["csv", "xlsx"], Query()] = "xlsx",
) -> Response:
    build, media_type = EXPORTS[format]
    return Response(
        _checked(build, deed),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="deed.{format}"'},
    )
