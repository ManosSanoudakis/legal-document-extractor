import copy

from accuracy import score_accuracy, values_match


def test_perfect_prediction(sample_truth):
    result = score_accuracy(copy.deepcopy(sample_truth), sample_truth)
    assert result["accuracy_pct"] == 100
    assert result["mismatches"] == []
    # 13 scalar fields + 3 parties x 4 + 1 representative x 4
    assert result["total"] == 13 + 12 + 4


def test_invented_value_is_wrong(sample_truth):
    truth = copy.deepcopy(sample_truth)
    truth["property"]["floor"] = None
    pred = copy.deepcopy(truth)
    pred["property"]["floor"] = "3ος όροφος"
    result = score_accuracy(pred, truth)
    assert [m["field"] for m in result["mismatches"]] == ["property.floor"]


def test_formatting_differences_are_tolerated(sample_truth):
    pred = copy.deepcopy(sample_truth)
    pred["sellers"][0]["full_name"] = "ΓΕΩΡΓΙΟΣ ΥΠΟΘΕΤΙΚΟΣ"           # no accents, no patronymic
    pred["sellers"][0]["id_document"] = "AK000101"                    # Latin letters, no space
    pred["notary"]["registry_number"] = "12345"
    pred["property"]["kaek"] = "9999 0100 0012 / 0 / 5"
    pred["property"]["floor"] = "2"
    pred["transaction"]["price"] = "185.000,00"
    pred["transaction"]["date"] = "15/03/2024"
    assert score_accuracy(pred, sample_truth)["accuracy_pct"] == 100


def test_party_order_does_not_matter(sample_truth):
    pred = copy.deepcopy(sample_truth)
    pred["sellers"].reverse()
    assert score_accuracy(pred, sample_truth)["accuracy_pct"] == 100


def test_missing_and_extra_parties(sample_truth):
    pred = copy.deepcopy(sample_truth)
    pred["sellers"] = pred["sellers"][:1]
    pred["buyers"].append({"full_name": "Κάποιος Άλλος", "tax_id": "555555555", "id_document": None, "address": None})
    result = score_accuracy(pred, sample_truth)
    assert sum(m["field"].startswith("sellers[1]") for m in result["mismatches"]) == 4
    assert result["extra_parties"] == 1


def test_empty_placeholder_parties_are_ignored(sample_truth):
    pred = copy.deepcopy(sample_truth)
    pred["legal_representatives"].append(dict.fromkeys(pred["legal_representatives"][0]))
    assert score_accuracy(pred, sample_truth)["extra_parties"] == 0


def test_values_match_edge_cases():
    assert values_match("text", None, None)
    assert not values_match("text", "Αθήνα", None)
    assert not values_match("text", "Αθήνα", "Πάτρα")
    assert not values_match("text", "Αθ", "Αθήνα")  # too short to count as a prefix
    assert values_match("number", 85.4, "85,40")
    assert not values_match("number", 85.4, 854)
    assert values_match("floor", "ισόγειο", "Ισόγειο")
    assert not values_match("exact", "sale", "donation")
