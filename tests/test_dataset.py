"""The labelled deeds must be internally consistent, or accuracy numbers mean nothing."""
import json
from pathlib import Path

import fitz
import pytest

from accuracy import score_accuracy
from schema import Deed
from validators import afm_is_valid

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
TRUTH_FILES = [SAMPLES / "sample_deed.json", *sorted((SAMPLES / "dataset").glob("*.json"))]


@pytest.mark.parametrize("truth_path", TRUTH_FILES, ids=lambda p: p.stem)
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


@pytest.mark.parametrize("scanned", sorted((SAMPLES / "dataset_scanned").glob("*.pdf")), ids=lambda p: p.stem)
def test_scanned_copies_share_ground_truth(scanned):
    clean = SAMPLES / "dataset" / scanned.name
    def truth(pdf):
        return pdf.with_suffix(".json").read_text(encoding="utf-8")

    assert truth(scanned) == truth(clean)
    with fitz.open(scanned) as doc, fitz.open(clean) as original:
        assert doc.page_count == original.page_count
        assert all(page.get_text().strip() == "" for page in doc), "scans must have no text layer"
