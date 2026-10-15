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


def test_validate_edited_deed(client, sample_truth):
    issues = client.post("/api/validate", json=sample_truth).json()["issues"]
    assert any(i["field"] == "sellers[0].tax_id" for i in issues)
    assert client.post("/api/validate", json={"sellers": "not a list"}).status_code == 422


def test_export_xlsx_and_csv(client, sample_truth):
    import io

    from openpyxl import load_workbook

    response = client.post("/api/export?format=xlsx", json=sample_truth)
    assert response.status_code == 200
    assert 'filename="deed.xlsx"' in response.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(response.content))
    assert wb.sheetnames == ["Deed", "People"]
    people = list(wb["People"].values)
    assert people[1][:3] == ("Seller", sample_truth["sellers"][0]["full_name"], sample_truth["sellers"][0]["tax_id"])
    assert len(people) == 1 + 2 + 1 + 1  # header, 2 sellers, 1 buyer, 1 representative

    csv_text = client.post("/api/export?format=csv", json=sample_truth).content.decode("utf-8-sig")
    assert "Transaction,Price (EUR),185000" in csv_text
    assert client.post("/api/export?format=pdf", json=sample_truth).status_code == 422


def test_evaluate_upload_has_no_ground_truth(client, monkeypatch):
    seen = {}

    def fake_evaluation(pdf_path, api_key, truth=None):
        seen["truth"] = truth
        return {"models": []}

    monkeypatch.setattr(api, "run_evaluation", fake_evaluation)
    pdf = api.SAMPLE_PDF.read_bytes()
    response = client.post("/api/evaluate", headers=KEY, files={"file": ("mine.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    assert seen["truth"] is None
    assert response.json()["pdf"] == "mine.pdf"
