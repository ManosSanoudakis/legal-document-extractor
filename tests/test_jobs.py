import time

import pytest
from google.genai import errors as genai_errors

from deed_extractor import jobs
from deed_extractor.jobs import JobLimitError, JobStore
from deed_extractor.schema import ExtractionResult


def wait(store: JobStore, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = store.snapshot(job_id)
        if snap["status"] == "done":
            return snap
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def deed(price: int) -> ExtractionResult:
    return ExtractionResult(
        deed={"transaction": {"deed_type": "sale", "price": price, "date": "2024-01-01"}},
        meta={"model": "m"},
        validation=[{"field": "x", "message": "bad", "severity": "error"}],
    )


def test_documents_are_processed_in_order_with_stages():
    stages = []

    def run(data, on_stage):
        on_stage("reading")
        on_stage("extracting")
        stages.append(data)
        return deed(int(data))

    store = JobStore()
    job = store.submit([("a.pdf", b"1"), ("b.pdf", b"2")], run=run, model="m")
    snap = wait(store, job["id"])
    assert stages == [b"1", b"2"]
    assert snap["kind"] == "extract" and snap["model"] == "m"
    assert [d["status"] for d in snap["documents"]] == ["done", "done"]
    assert snap["documents"][1]["summary"] == {"deed_type": "sale", "price": 2, "date": "2024-01-01",
                                               "flags": 1, "errors": 1}
    first = snap["documents"][0]
    assert store.result(job["id"], first["id"]).deed["transaction"]["price"] == 1
    assert "result" not in first  # progress polls stay small


def test_bad_key_stops_the_rest_and_the_key_is_dropped():
    calls = []

    def run(data, on_stage):
        calls.append(data)
        raise genai_errors.APIError(400, {"error": {"message": "API key not valid. Please pass a valid API key."}})

    store = JobStore()
    job = store.submit([("a.pdf", b"1"), ("b.pdf", b"2"), ("c.pdf", b"3")], run=run)
    snap = wait(store, job["id"])
    assert calls == [b"1"]  # not tried again for every document
    assert snap["documents"][0]["error"] == "Gemini rejected the API key."
    assert all(d["error"].startswith("Not processed") for d in snap["documents"][1:])
    stored = store._jobs[job["id"]]
    assert stored.run is None and all(d.data is None for d in stored.documents)  # the task held the key


def test_one_bad_document_does_not_stop_the_job():
    def run(data, on_stage):
        if data == b"bad":
            raise ValueError("broken PDF")
        return deed(1)

    store = JobStore()
    snap = wait(store, store.submit([("bad.pdf", b"bad"), ("ok.pdf", b"1")], run)["id"])
    assert [d["status"] for d in snap["documents"]] == ["error", "done"]
    assert snap["documents"][0]["error"] == "Could not process this document."


def test_too_many_active_jobs_are_refused(monkeypatch):
    import threading

    release = threading.Event()
    def run(*args):
        return release.wait(5) and deed(1)

    store = JobStore(workers=1)
    try:
        for _ in range(jobs.MAX_ACTIVE_JOBS):
            store.submit([("a.pdf", b"1")], run)
        with pytest.raises(JobLimitError):
            store.submit([("a.pdf", b"1")], run)
    finally:
        release.set()


def test_other_results_have_no_summary():
    store = JobStore()
    snap = wait(store, store.submit([("a.pdf", b"1")], lambda *args: {"models": []}, kind="evaluate")["id"])
    assert snap["documents"][0]["status"] == "done" and snap["documents"][0]["summary"] is None


def test_on_done_failure_keeps_the_result():
    def on_done(job, doc):
        raise RuntimeError("database down")

    store = JobStore(on_done=on_done)
    snap = wait(store, store.submit([("a.pdf", b"1")], lambda *args: deed(1))["id"])
    assert snap["documents"][0]["status"] == "done"
