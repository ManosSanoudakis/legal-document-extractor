"""
Background extraction jobs.

A job is one or more PDFs extracted with the same model and API key. It runs
in a worker thread, one document at a time (free-tier rate limits are per
minute and per day), while the browser polls its progress. Nothing is
written to disk here: a PDF's bytes are dropped as soon as it is processed,
and the API key once the job ends.

If Gemini rejects the key or the quota runs out, the rest of the job is
stopped rather than failing the same way once per document.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

MAX_RUNNING_JOBS = 2     # jobs processed at the same time
MAX_ACTIVE_JOBS = 4      # queued + running; more is refused
JOB_TTL_SECONDS = 3600   # finished jobs are forgotten after this

ACTIVE = {"queued", "reading", "extracting"}


class JobLimitError(Exception):
    """Too many jobs are already queued or running."""


class StopJob(Exception):
    """An error that will hit every remaining document too (bad key, quota)."""


@dataclass
class JobDocument:
    id: str
    filename: str
    data: bytes | None
    status: str = "queued"   # queued → reading → extracting → done | error
    error: str | None = None
    result: dict | None = None
    started: float | None = None
    finished: float | None = None
    extra: dict = field(default_factory=dict)   # e.g. the history id, set by on_done


@dataclass
class Job:
    id: str
    model: str
    api_key: str | None
    documents: list[JobDocument]
    created: float = field(default_factory=time.time)
    finished: float | None = None


def describe_error(exc: Exception) -> tuple[str, bool]:
    """A message for the user, and whether the rest of the job should stop."""
    if isinstance(exc, genai_errors.APIError):
        text = str(exc)
        if exc.code in (401, 403) or "API_KEY_INVALID" in text or "API key not valid" in text:
            return "Gemini rejected the API key.", True
        if exc.code == 429:
            return "Gemini rate limit or quota reached. Try again later.", True
        return f"Gemini request failed ({exc.code}).", False
    return "Could not process this document.", False


def summary(result: dict | None) -> dict | None:
    """The few values the batch table shows; the full result is fetched separately."""
    if result is None:
        return None
    txn = result.get("transaction") or {}
    issues = result.get("_validation") or []
    return {
        "deed_type": txn.get("deed_type"),
        "price": txn.get("price"),
        "date": txn.get("date"),
        "flags": len(issues),
        "errors": sum(1 for i in issues if i.get("severity") == "error"),
    }


class JobStore:
    """In-memory jobs, processed by a small thread pool."""

    def __init__(
        self,
        run: Callable[..., dict],
        on_done: Callable[[Job, JobDocument], None] | None = None,
        workers: int = MAX_RUNNING_JOBS,
    ) -> None:
        # run(pdf_bytes, api_key, model, on_stage) -> result; injected so tests need no model
        self._run = run
        self._on_done = on_done
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")

    def submit(self, files: list[tuple[str, bytes]], model: str, api_key: str) -> dict:
        with self._lock:
            self._purge()
            active = sum(1 for j in self._jobs.values() if j.finished is None)
            if active >= MAX_ACTIVE_JOBS:
                raise JobLimitError
            job = Job(
                id=uuid.uuid4().hex,
                model=model,
                api_key=api_key,
                documents=[JobDocument(id=uuid.uuid4().hex, filename=name, data=data) for name, data in files],
            )
            self._jobs[job.id] = job
        self._pool.submit(self._process, job)
        return self.snapshot(job.id)

    def snapshot(self, job_id: str) -> dict | None:
        """Progress of a job, without the full results (see result())."""
        with self._lock:
            self._purge()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            now = time.time()
            return {
                "id": job.id,
                "model": job.model,
                "status": "running" if job.finished is None else "done",
                "documents": [
                    {
                        "id": d.id,
                        "filename": d.filename,
                        "status": d.status,
                        "error": d.error,
                        "elapsed_seconds": round((d.finished or now) - d.started, 1) if d.started else None,
                        "summary": summary(d.result),
                        **d.extra,
                    }
                    for d in job.documents
                ],
            }

    def result(self, job_id: str, doc_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            doc = next((d for d in job.documents if d.id == doc_id), None) if job else None
            return doc.result if doc else None

    def _purge(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        for job_id in [j.id for j in self._jobs.values() if j.finished and j.finished < cutoff]:
            del self._jobs[job_id]

    def _set(self, doc: JobDocument, **changes) -> None:
        with self._lock:
            for name, value in changes.items():
                setattr(doc, name, value)

    def _process(self, job: Job) -> None:
        stop: str | None = None
        for doc in job.documents:
            if stop:
                self._set(doc, status="error", error=f"Not processed: {stop}", data=None)
                continue
            self._set(doc, status="reading", started=time.time())
            try:
                result = self._run(doc.data, job.api_key, job.model, lambda stage, d=doc: self._set(d, status=stage))
            except Exception as exc:  # noqa: BLE001 — every failure is reported on its document
                message, fatal = describe_error(exc)
                if not fatal:
                    logger.warning("Job %s: %s failed: %s", job.id[:8], doc.filename, exc)
                self._set(doc, status="error", error=message, finished=time.time(), data=None)
                stop = message if fatal else None
                continue
            self._set(doc, result=result, data=None)
            # Before "done", so whoever fetches the result also sees what on_done added
            if self._on_done:
                try:
                    self._on_done(job, doc)
                except Exception:  # noqa: BLE001 — saving to history must not lose the result
                    logger.exception("Job %s: on_done failed for %s", job.id[:8], doc.filename)
            self._set(doc, status="done", finished=time.time())
        with self._lock:
            job.finished = time.time()
            job.api_key = None  # the key lives only as long as the job
