import pytest
from fastapi.testclient import TestClient

import api

KEY = {"X-Gemini-Key": "test-key"}


@pytest.fixture
def client():
    return TestClient(api.app)


def test_config(client):
    body = client.get("/api/config").json()
    assert body["models"] == api.GeminiExtractor.MODELS
    assert body["sample_available"] is True


def test_extract_requires_key(client):
    response = client.post("/api/extract", data={"use_sample": "true"})
    assert response.status_code == 401


def test_extract_rejects_non_pdf(client):
    response = client.post("/api/extract", headers=KEY, files={"file": ("a.pdf", b"hello", "application/pdf")})
    assert response.status_code == 415


def test_extract_rejects_unknown_model(client):
    response = client.post("/api/extract", headers=KEY, data={"use_sample": "true", "model": "gpt-4"})
    assert response.status_code == 400


def test_extract_sample(client, monkeypatch):
    seen = {}

    def fake_pipeline(pdf_path, api_key, model_name):
        seen.update(api_key=api_key, model=model_name)
        return {"notary": {"name": "Test"}}

    monkeypatch.setattr(api, "run_pipeline", fake_pipeline)
    response = client.post("/api/extract", headers=KEY, data={"use_sample": "true"})
    assert response.status_code == 200
    assert response.json() == {"notary": {"name": "Test"}}
    assert seen == {"api_key": "test-key", "model": api.GeminiExtractor.MODELS[0]}


def test_evaluate_sample_uses_ground_truth(client, monkeypatch, sample_truth):
    seen = {}

    def fake_evaluation(pdf_path, api_key, truth=None):
        seen["truth"] = truth
        return {"models": [{"model": "m", "error": None}]}

    monkeypatch.setattr(api, "run_evaluation", fake_evaluation)
    response = client.post("/api/evaluate", headers=KEY, data={"use_sample": "true"})
    assert response.status_code == 200
    assert seen["truth"] == sample_truth


def test_evaluate_upload_has_no_ground_truth(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(api, "run_evaluation", lambda pdf_path, api_key, truth=None: seen.update(truth=truth) or {"models": []})
    pdf = api.SAMPLE_PDF.read_bytes()
    response = client.post("/api/evaluate", headers=KEY, files={"file": ("mine.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    assert seen["truth"] is None
    assert response.json()["pdf"] == "mine.pdf"
