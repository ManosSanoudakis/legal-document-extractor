import json
from types import SimpleNamespace

import pytest
from PIL import Image

import extractor
from schema import Deed


@pytest.fixture
def page_images(tmp_path):
    paths = []
    for i in range(2):
        path = tmp_path / f"{i}.jpeg"
        Image.new("RGB", (10, 10), "white").save(path)
        paths.append(path)
    return paths


class FakeClient:
    """Stands in for genai.Client and records the request."""

    def __init__(self, response):
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate)
        self._response = response

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def run_extract(monkeypatch, page_images, response):
    client = FakeClient(response)
    monkeypatch.setattr(extractor.genai, "Client", lambda api_key, **kwargs: client)
    result = extractor.GeminiExtractor("key", "gemini-test").extract(page_images)
    return result, client


def test_requests_structured_output(monkeypatch, page_images, sample_truth):
    response = SimpleNamespace(parsed=Deed.model_validate({**sample_truth, "sources": []}), text=None)
    result, client = run_extract(monkeypatch, page_images, response)

    [call] = client.calls
    assert call["model"] == "gemini-test"
    assert call["config"].response_schema is Deed
    assert call["config"].response_mime_type == "application/json"
    # each page is preceded by its label, then the prompt
    assert call["contents"][0] == "Σελίδα 1:" and call["contents"][2] == "Σελίδα 2:"
    assert len(call["contents"]) == 5

    assert result["transaction"]["deed_type"] == "sale"
    assert result["_meta"]["pages"] == 2
    assert any(i["field"].endswith("tax_id") for i in result["_validation"])  # sample ΑΦΜ are invalid


def test_client_retries_busy_and_server_errors():
    retry = extractor.HTTP_OPTIONS.retry_options
    assert retry.attempts == 3
    assert {429, 503} <= set(retry.http_status_codes)


def test_falls_back_to_text_when_parsed_missing(monkeypatch, page_images, sample_truth):
    response = SimpleNamespace(parsed=None, text=json.dumps(sample_truth, ensure_ascii=False))
    result, _ = run_extract(monkeypatch, page_images, response)
    assert result["notary"]["name"] == sample_truth["notary"]["name"]


def test_off_schema_json_is_kept(monkeypatch, page_images):
    response = SimpleNamespace(parsed=None, text='```json\n{"notary": {"name": "X"}}\n```')
    result, _ = run_extract(monkeypatch, page_images, response)
    assert result["notary"] == {"name": "X"}
    assert "_error" not in result


def test_unparseable_response_returns_empty_deed(monkeypatch, page_images):
    response = SimpleNamespace(parsed=None, text=None)  # e.g. hit the token cap
    result, _ = run_extract(monkeypatch, page_images, response)
    assert "_error" in result
    assert result["sellers"] == [] and result["property"]["kaek"] is None


def test_models_can_be_overridden(monkeypatch):
    import importlib

    monkeypatch.setenv("GEMINI_MODELS", "model-a, model-b")
    try:
        assert importlib.reload(extractor).MODELS == ["model-a", "model-b"]
    finally:
        monkeypatch.delenv("GEMINI_MODELS")
        importlib.reload(extractor)


def test_page_text_is_sent_and_checked(monkeypatch, page_images, sample_truth):
    """A digital PDF's text goes with each page, and values missing from it are flagged."""
    misread = {**sample_truth, "sources": []}
    misread["property"] = {**misread["property"], "kaek": "999910000012/0/5"}  # two digits swapped
    response = SimpleNamespace(parsed=Deed.model_validate(misread), text=None)
    client = FakeClient(response)
    monkeypatch.setattr(extractor.genai, "Client", lambda api_key, **kwargs: client)
    texts = ["Σελίδα με ΚΑΕΚ 999901000012/0/5 " * 3, "Δεύτερη σελίδα με αρκετό κείμενο για να μετρήσει " * 2]
    result = extractor.GeminiExtractor("key", "gemini-test").extract(page_images, texts)

    contents = client.calls[0]["contents"]
    assert contents[2].startswith("Κείμενο σελίδας 1") and texts[0] in contents[2]
    assert contents[3] == "Σελίδα 2:"
    assert result["_meta"]["text_layer"] is True
    assert any(i["field"] == "property.kaek" and "PDF's text" in i["message"] for i in result["_validation"])


def test_scanned_pages_have_no_text_layer(tmp_path):
    from pathlib import Path

    samples = Path(__file__).resolve().parent.parent / "samples"
    assert all(extractor.pdf_page_texts(str(samples / "sample_deed.pdf")))
    assert not any(extractor.pdf_page_texts(str(samples / "dataset_scanned" / "deed_01.pdf")))
