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
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Iterator

import fitz
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from google.genai import errors as genai_errors

from evaluate import run_evaluation
from extractor import GeminiExtractor, run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

SAMPLE_PDF = Path(__file__).parent / "samples" / "sample_deed.pdf"
SAMPLE_TRUTH = SAMPLE_PDF.with_suffix(".json")  # correct answers for the sample
MAX_FILE_MB = 20
MAX_PAGES = 30

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
    if errors and len(errors) == len(report["models"]):
        if all("API key" in e or "API_KEY_INVALID" in e for e in errors):
            raise HTTPException(401, "Gemini rejected the API key.")
    return report
