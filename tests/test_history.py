import time

import pytest

from history import History


@pytest.fixture
def history(tmp_path):
    return History(tmp_path / "h.sqlite3")


def result(price: int = 100) -> dict:
    return {
        "transaction": {"deed_type": "sale", "price": price, "date": "2024-01-01"},
        "_validation": [
            {"field": "sellers[0].tax_id", "severity": "error"},
            {"field": "sellers[0].tax_id", "severity": "warning"},
            {"field": "property.kaek", "severity": "warning"},
        ],
        "_meta": {"model": "m"},
    }


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
    assert history.get("nope") is None


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
