# The API has no logins and is meant to run locally or behind your own access
# control: everyone who can reach it shares one history. Each caller sends their
# own Gemini key per request (X-Gemini-Key); it is never stored or logged. See
# "Security" in docs/design.md for what is protected and what a hosted version needs.
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

from . import demo
from .evaluate import EvaluationReport, run_evaluation
from .export import batch_to_csv, batch_to_xlsx, to_csv, to_xlsx
from .extractor import MAX_RECHECK_FIELDS, GeminiExtractor, recheck_lines, run_pipeline, run_recheck
from .history import History
from .jobs import Job, JobDocument, JobLimitError, JobStore, Task
from .schema import ExtractionResult
from .validators import validate_deed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PDF = ROOT / "samples" / "sample_deed.pdf"
SAMPLE_TRUTH = SAMPLE_PDF.with_suffix(".json")  # correct answers for the sample
MAX_FILE_MB = 20
MAX_PAGES = 30
MAX_BATCH_FILES = 20

app = FastAPI(
    title="Legal Document Extractor API",
    description="Extract structured data from Greek notarial deeds with Gemini vision.",
    version="3.0.0",
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


def read_upload(file: UploadFile) -> bytes:
    """An uploaded PDF's bytes, enforcing size and page limits."""
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


def read_documents(
    files: list[UploadFile] | None, use_sample: bool, demo_id: str | None, many: bool,
) -> tuple[list[tuple[str, bytes]], dict | None]:
    """The PDFs to process as (file name, bytes), and their correct values when known (sample, demos)."""
    if use_sample:
        if not SAMPLE_PDF.exists():
            raise HTTPException(404, "Sample document is not available.")
        truth = json.loads(SAMPLE_TRUTH.read_text(encoding="utf-8")) if SAMPLE_TRUTH.exists() else None
        return [(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())], truth
    if demo_id:
        path = demo.pdf_path(demo_id)
        if path is None:
            raise HTTPException(404, "No such demo deed.")
        return [(path.name, path.read_bytes())], demo.truth(demo_id)

    if not files:
        raise HTTPException(400, "Upload a PDF, or set use_sample=true or demo.")
    limit = MAX_BATCH_FILES if many else 1
    if len(files) > limit:
        raise HTTPException(413, f"At most {MAX_BATCH_FILES} files per batch." if many else "Send one PDF.")
    documents = []
    for f in files:
        try:
            documents.append((f.filename or "upload.pdf", read_upload(f)))
        except HTTPException as exc:
            raise HTTPException(exc.status_code, f"{f.filename}: {exc.detail}") from None
    return documents, None


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

# ---------------------------------------------------------------------------
# Background tasks: each closes over its settings and the API key
# ---------------------------------------------------------------------------

def extract_task(api_key: str, model: str) -> Task:
    def run(data: bytes, on_stage) -> ExtractionResult:
        with pdf_on_disk(data) as path:
            return run_pipeline(pdf_path=path, api_key=api_key, model_name=model, on_stage=on_stage)
    return run


def evaluate_task(api_key: str, truth: dict | None, filename: str) -> Task:
    def run(data: bytes, on_stage) -> EvaluationReport:
        with pdf_on_disk(data) as path:
            # If every model fails the same way (e.g. a rejected key), the job reports that error
            report = run_evaluation(
                pdf_path=path, api_key=api_key, truth=truth, on_stage=on_stage, raise_if_all_failed=True,
            )
        report.pdf = filename
        return report
    return run


def recheck_task(api_key: str, model: str, deed: dict, fields: list[str]) -> Task:
    def run(data: bytes, on_stage):
        with pdf_on_disk(data) as path:
            return run_recheck(
                pdf_path=path, api_key=api_key, deed=deed, fields=fields, model_name=model, on_stage=on_stage,
            )
    return run


def parse_recheck(deed: str | None, fields: str | None) -> tuple[dict, list[str]]:
    try:
        current, wanted = json.loads(deed or "{}"), json.loads(fields or "[]")
    except json.JSONDecodeError:
        raise HTTPException(422, "deed and fields must be JSON.") from None
    if not isinstance(current, dict) or not isinstance(wanted, list) or not all(isinstance(f, str) for f in wanted):
        raise HTTPException(422, "deed must be an object and fields a list of field paths.")
    if not 1 <= len(wanted) <= MAX_RECHECK_FIELDS:
        raise HTTPException(422, f"Re-check between 1 and {MAX_RECHECK_FIELDS} fields.")
    try:
        recheck_lines(current, wanted)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return current, wanted


# Where saved results live:
# - "server": one shared SQLite history, for a single user or an office behind its own access control
# - "browser": each visitor's own history, kept in their browser; the server stores nothing
HISTORY_MODE = os.environ.get("HISTORY", "server").strip().lower() or "server"
if HISTORY_MODE not in ("server", "browser"):
    raise RuntimeError(f"HISTORY must be 'server' or 'browser', not {HISTORY_MODE!r}")

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
HISTORY = History(
    DATA_DIR / "history.sqlite3",
    retention_days=float(os.environ["HISTORY_RETENTION_DAYS"]) if os.environ.get("HISTORY_RETENTION_DAYS") else None,
) if HISTORY_MODE == "server" else None


def server_history() -> History:
    if HISTORY is None:
        raise HTTPException(404, "History is kept in each visitor's browser on this server.")
    return HISTORY


def save_to_history(job: Job, doc: JobDocument) -> None:
    """Every finished extraction goes to history; its id travels with the result so edits can be saved."""
    if job.kind != "extract" or HISTORY is None:
        return
    history_id = HISTORY.add(doc.filename, job.model or "", doc.result)
    doc.result.meta.history_id = history_id
    doc.extra["history_id"] = history_id


JOBS = JobStore(on_done=save_to_history)

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
        "demos": demo.demos(),
        "max_file_mb": MAX_FILE_MB,
        "max_pages": MAX_PAGES,
        "max_batch_files": MAX_BATCH_FILES,
        "history": HISTORY_MODE,
    }


def inline_pdf(path: Path) -> FileResponse:
    # inline, so the browser shows it in the preview instead of downloading it
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@app.get("/api/sample")
def sample() -> FileResponse:
    if not SAMPLE_PDF.exists():
        raise HTTPException(404, "Sample document is not available.")
    return inline_pdf(SAMPLE_PDF)


@app.get("/api/demo/{demo_id}")
def demo_result(demo_id: str) -> ExtractionResult:
    """A saved answer for a demo deed: no API key, no model call."""
    result = demo.result(demo_id)
    if result is None:
        raise HTTPException(404, "No such demo deed.")
    return result


@app.get("/api/demo/{demo_id}/pdf")
def demo_pdf(demo_id: str) -> FileResponse:
    path = demo.pdf_path(demo_id)
    if path is None:
        raise HTTPException(404, "No such demo deed.")
    return inline_pdf(path)


@app.post("/api/jobs", status_code=202)
def create_job(
    x_gemini_key: Annotated[str | None, Header()] = None,
    task: Annotated[Literal["extract", "evaluate", "recheck"], Form()] = "extract",
    model: Annotated[str, Form()] = GeminiExtractor.MODELS[0],
    use_sample: Annotated[bool, Form()] = False,
    demo_id: Annotated[str | None, Form(alias="demo")] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    deed: Annotated[str | None, Form()] = None,
    fields: Annotated[str | None, Form()] = None,
) -> dict:
    """Start work that takes a while; poll GET /api/jobs/{id} for progress.

    - extract: one or more PDFs with one model. Each result is saved to history.
    - evaluate: one PDF with every model, compared (and scored, for the sample and demo deeds).
    - recheck: one PDF, with `deed` and `fields` (JSON): those fields read again.
    """
    api_key = require_api_key(x_gemini_key)
    if task != "evaluate" and model not in GeminiExtractor.MODELS:
        raise HTTPException(400, f"Unknown model '{model}'.")
    if task == "recheck":
        current, wanted = parse_recheck(deed, fields)
    documents, truth = read_documents(files, use_sample, demo_id, many=task == "extract")

    if task == "extract":
        run = extract_task(api_key, model)
    elif task == "evaluate":
        run, model = evaluate_task(api_key, truth, documents[0][0]), None
    else:
        run = recheck_task(api_key, model, current, wanted)

    try:
        job = JOBS.submit(documents, run=run, kind=task, model=model)
    except JobLimitError:
        raise HTTPException(429, "Too many jobs are running. Try again in a minute.") from None
    logger.info("Job %s started — task=%s model=%s documents=%d", job["id"][:8], task, model, len(documents))
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = JOBS.snapshot(job_id)
    if job is None:
        raise HTTPException(404, "No such job (finished jobs are kept for an hour).")
    return job


@app.get("/api/jobs/{job_id}/documents/{doc_id}")
def job_result(job_id: str, doc_id: str):
    """One document's result: an ExtractionResult, an evaluation report or a RecheckResult, by the job's task."""
    result = JOBS.result(job_id, doc_id)
    if result is None:
        raise HTTPException(404, "No result for this document (yet).")
    return result


@app.get("/api/history")
def history_list() -> list[dict]:
    return server_history().list()


@app.get("/api/history/{doc_id}")
def history_get(doc_id: str) -> dict:
    record = server_history().get(doc_id)
    if record is None:
        raise HTTPException(404, "No such document in history.")
    return record


@app.put("/api/history/{doc_id}")
def history_update(
    doc_id: str,
    edited: Annotated[dict | None, Body()] = None,
    reviewed: Annotated[list[str], Body()] = [],  # noqa: B006 — FastAPI copies defaults per request
) -> dict:
    """Save the user's corrections (null = none) and the fields they have checked."""
    if not server_history().update(doc_id, edited, reviewed):
        raise HTTPException(404, "No such document in history.")
    return {"saved": True}


@app.delete("/api/history/{doc_id}", status_code=204)
def history_delete(doc_id: str) -> Response:
    if not server_history().delete(doc_id):
        raise HTTPException(404, "No such document in history.")
    return Response(status_code=204)


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
