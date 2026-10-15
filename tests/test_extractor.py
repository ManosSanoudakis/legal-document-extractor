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
    monkeypatch.setattr(extractor.genai, "Client", lambda api_key: client)
    result = extractor.GeminiExtractor("key", "gemini-test").extract(page_images)
    return result, client


def test_requests_structured_output(monkeypatch, page_images, sample_truth):
    response = SimpleNamespace(parsed=Deed.model_validate(sample_truth), text=None)
    result, client = run_extract(monkeypatch, page_images, response)

    [call] = client.calls
    assert call["model"] == "gemini-test"
    assert call["config"].response_schema is Deed
    assert call["config"].response_mime_type == "application/json"
    assert len(call["contents"]) == 3  # two pages + prompt

    assert result["transaction"]["deed_type"] == "sale"
    assert result["_meta"]["pages"] == 2
    assert any(i["field"].endswith("tax_id") for i in result["_validation"])  # sample ΑΦΜ are invalid


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
