import json
import time

import pytest

from deed_extractor.history import History
from deed_extractor.schema import ExtractionResult


@pytest.fixture
def history(tmp_path):
    return History(tmp_path / "h.sqlite3")


def result(price: int = 100) -> ExtractionResult:
    return ExtractionResult(
        deed={"transaction": {"deed_type": "sale", "price": price, "date": "2024-01-01"}},
        meta={"model": "m"},
        validation=[
            {"field": "sellers[0].tax_id", "message": "a", "severity": "error"},
            {"field": "sellers[0].tax_id", "message": "b", "severity": "warning"},
            {"field": "property.kaek", "message": "c", "severity": "warning"},
        ],
    )


def test_add_list_get(history):
    first = history.add("a.pdf", "m", result(1))
    time.sleep(0.01)
    second = history.add("b.pdf", "m", result(2))
    listed = history.list()
    assert [i["id"] for i in listed] == [second, first]  # newest first
    assert listed[0]["summary"] == {"deed_type": "sale", "price": 2, "date": "2024-01-01",
                                    "flags": 3, "errors": 1, "to_check": 2}  # 2 distinct fields
    record = history.get(first)
    assert record["filename"] == "a.pdf" and record["edited"] is None and record["reviewed"] == []
    assert record["result"].deed["transaction"]["price"] == 1
    assert record["result"].meta.history_id == first  # so the UI can save edits
    assert history.get("nope") is None


def test_results_saved_in_the_old_shape_still_load(history):
    """Before ExtractionResult, the deed's keys were at the top level, next to _meta and _validation."""
    doc = history.add("a.pdf", "m", result())
    old = {"transaction": {"price": 5}, "_meta": {"pages": 2}, "_error": "bad JSON",
           "_validation": [{"field": "property.kaek", "value": None, "message": "x", "severity": "warning"}]}
    history._run("UPDATE documents SET result = ? WHERE id = ?", (json.dumps(old), doc))
    loaded = history.get(doc)["result"]
    assert loaded.deed == {"transaction": {"price": 5}}
    assert loaded.meta.model == "m" and loaded.meta.pages == 2 and loaded.error == "bad JSON"
    assert history.list()[0]["summary"]["to_check"] == 1


def test_corrections_and_review_are_saved(history):
    doc = history.add("a.pdf", "m", result(1))
    corrected = {"transaction": {"deed_type": "sale", "price": 999, "date": "2024-01-01"}}
    assert history.update(doc, corrected, ["property.kaek"])
    item = history.list()[0]
    assert item["edited"] is True
    assert item["summary"]["price"] == 999  # the list shows the corrected values
    assert item["summary"]["to_check"] == 1
    assert history.get(doc)["edited"] == corrected
    assert history.update(doc, None, [])  # undo
    assert history.get(doc)["edited"] is None
    assert not history.update("nope", None, [])


def test_delete_and_retention(tmp_path, history):
    doc = history.add("a.pdf", "m", result())
    assert history.delete(doc) and not history.delete(doc)

    short = History(tmp_path / "short.sqlite3", retention_days=1 / 86400)  # one second
    short.add("old.pdf", "m", result())
    time.sleep(1.2)
    assert short.list() == []
