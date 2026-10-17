"""The labelled deeds must be internally consistent, or accuracy numbers mean nothing."""
import json
from pathlib import Path

import fitz
import pytest

from accuracy import score_accuracy
from schema import Deed
from validators import afm_is_valid

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
TRUTH_FILES = [
    SAMPLES / "sample_deed.json",
    *sorted((SAMPLES / "dataset").glob("*.json")),
    *sorted((SAMPLES / "dataset_long").glob("*.json")),
    *sorted((SAMPLES / "dataset_varied").glob("*.json")),
]
LONG_PDFS = sorted((SAMPLES / "dataset_long").glob("*.pdf")) + sorted((SAMPLES / "dataset_varied").glob("*.pdf"))
# (scanned folder, the clean folder it was made from)
SCAN_SETS = [("dataset_scanned", "dataset"), ("dataset_varied_scanned", "dataset_varied")]


@pytest.mark.parametrize("truth_path", TRUTH_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_truth_matches_schema_and_pdf(truth_path):
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    Deed.model_validate({**truth, "sources": []})
    assert score_accuracy(truth, truth)["accuracy_pct"] == 100

    text = " ".join(page.get_text() for page in fitz.open(truth_path.with_suffix(".pdf")))
    text = " ".join(text.split())
    people = truth["sellers"] + truth["buyers"] + truth["legal_representatives"]
    for person in people:
        assert person["tax_id"] in text
        assert not afm_is_valid(person["tax_id"]), "dataset must never contain a valid ΑΦΜ"
    assert truth["property"]["kaek"] in text
    assert truth["notary"]["registry_number"] in text


def test_dataset_exists():
    assert len(TRUTH_FILES) > 1, "Run: python samples/make_sample_deed.py --dataset 10"


@pytest.mark.parametrize(
    "scanned",
    [pdf for folder, _ in SCAN_SETS for pdf in sorted((SAMPLES / folder).glob("*.pdf"))],
    ids=lambda p: f"{p.parent.name}/{p.stem}",
)
def test_scanned_copies_share_ground_truth(scanned):
    clean = SAMPLES / dict(SCAN_SETS)[scanned.parent.name] / scanned.name
    def truth(pdf):
        return pdf.with_suffix(".json").read_text(encoding="utf-8")

    assert truth(scanned) == truth(clean)
    with fitz.open(scanned) as doc, fitz.open(clean) as original:
        assert doc.page_count == original.page_count
        assert all(page.get_text().strip() == "" for page in doc), "scans must have no text layer"


@pytest.mark.parametrize("pdf", LONG_PDFS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_long_deeds_hold_look_alikes_but_never_a_valid_afm(pdf):
    """Long deeds must be long, carry other tax IDs and ΚΑΕΚ, and still contain no real ΑΦΜ."""
    import re

    truth = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    with fitz.open(pdf) as doc:
        assert doc.page_count >= 5
        text = " ".join(" ".join(page.get_text() for page in doc).split())
    afms = set(re.findall(r"Α\.Φ\.Μ\.:? (\d{9})", text))
    real = {p["tax_id"] for p in truth["sellers"] + truth["buyers"] + truth["legal_representatives"]}
    assert afms > real, "expected tax IDs of people who are not parties"
    assert not any(afm_is_valid(a) for a in afms)


@pytest.mark.parametrize("truth_path", TRUTH_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_correct_values_are_found_in_the_text_layer(truth_path):
    """No false alarms: the true values of every labelled deed pass the text-layer check."""
    from extractor import pdf_page_texts
    from validators import validate_deed

    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    texts = pdf_page_texts(str(truth_path.with_suffix(".pdf")))
    assert all(texts)
    issues = validate_deed({**truth, "sources": []}, text=" ".join(texts))
    assert [i for i in issues if "PDF's text" in i["message"]] == []
