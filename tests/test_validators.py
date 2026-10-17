import copy
from datetime import date

from conftest import make_valid_afm

from validators import afm_is_valid, get_path, validate_deed

TODAY = date(2026, 10, 15)


def clean_deed(sample_truth: dict) -> dict:
    """The sample deed with valid tax IDs, so it should pass every check."""
    deed = copy.deepcopy(sample_truth)
    for i, p in enumerate(deed["sellers"] + deed["buyers"] + deed["legal_representatives"]):
        p["tax_id"] = make_valid_afm(f"1000000{i}")
    return deed


def fields(issues: list[dict]) -> set[str]:
    return {i["field"] for i in issues}


def test_afm_check_digit():
    assert afm_is_valid(make_valid_afm("12345678"))
    assert not afm_is_valid("123456789")
    assert not afm_is_valid("000000000")
    assert not afm_is_valid("12345")
    assert not afm_is_valid("12345678X")


def test_clean_deed_passes(sample_truth):
    assert validate_deed(clean_deed(sample_truth), today=TODAY) == []


def test_sample_tax_ids_are_flagged(sample_truth):
    # The fictional sample uses invalid ΑΦΜ on purpose
    issues = validate_deed(sample_truth, today=TODAY)
    expected = {"sellers[0].tax_id", "sellers[1].tax_id", "buyers[0].tax_id", "legal_representatives[0].tax_id"}
    assert expected <= fields(issues)
    assert all(i["severity"] == "error" for i in issues if i["field"].endswith("tax_id"))


def test_tax_id_wrong_length(sample_truth):
    deed = clean_deed(sample_truth)
    deed["sellers"][0]["tax_id"] = "1234567"
    [issue] = validate_deed(deed, today=TODAY)
    assert issue["field"] == "sellers[0].tax_id" and "9 digits" in issue["message"]


def test_kaek_format(sample_truth):
    deed = clean_deed(sample_truth)
    deed["property"]["kaek"] = "05 02 30 60 00 01"  # spaces are fine
    assert validate_deed(deed, today=TODAY) == []
    deed["property"]["kaek"] = "99 99 01 00 00 00012/0/5"  # 15 digits
    assert fields(validate_deed(deed, today=TODAY)) == {"property.kaek"}


def test_dates(sample_truth):
    deed = clean_deed(sample_truth)
    deed["transaction"]["date"] = "2027-01-01"
    assert "future" in validate_deed(deed, today=TODAY)[0]["message"]
    deed["transaction"]["date"] = "15/03/2024"
    assert "YYYY-MM-DD" in validate_deed(deed, today=TODAY)[0]["message"]


def test_amounts(sample_truth):
    deed = clean_deed(sample_truth)
    deed["transaction"]["price"] = 0
    deed["property"]["area_sqm"] = "85,4"
    assert fields(validate_deed(deed, today=TODAY)) == {"transaction.price", "property.area_sqm"}


def test_value_must_appear_in_its_quote(sample_truth):
    deed = clean_deed(sample_truth)
    afm = deed["sellers"][0]["tax_id"]
    deed["sources"] = [
        # spacing differs: fine
        {"field": "sellers[0].tax_id", "page": 1, "quote": f"με Α.Φ.Μ. {afm[:3]} {afm[3:]} και"},
        {"field": "notary.name", "page": 1, "quote": "ΕΛΕΝΗ ΠΑΠΑΔΗΜΗΤΡΙΟΥ-ΔΟΚΙΜΑΣΤΗ"},          # case/accents: fine
        {"field": "transaction.price", "page": 2, "quote": "185.000,00 €"},                        # converted: skipped
        {"field": "property.kaek", "page": 1, "quote": "ΚΑΕΚ 999901000099/0/5"},                   # wrong digits
        {"field": "buyers[5].tax_id", "page": 1, "quote": "x"},                                    # no such party
    ]
    assert fields(validate_deed(deed, today=TODAY)) == {"property.kaek"}


def test_get_path(sample_truth):
    assert get_path(sample_truth, "property.kaek") == sample_truth["property"]["kaek"]
    assert get_path(sample_truth, "sellers[1].full_name") == sample_truth["sellers"][1]["full_name"]
    assert get_path(sample_truth, "sellers[9].full_name") is None
    assert get_path(sample_truth, "nonsense") is None


def test_missing_parties_and_same_person_both_sides(sample_truth):
    deed = clean_deed(sample_truth)
    deed["buyers"][0]["tax_id"] = deed["sellers"][0]["tax_id"]
    assert "buyers[0].tax_id" in fields(validate_deed(deed, today=TODAY))
    deed["sellers"] = []
    assert "sellers" in fields(validate_deed(deed, today=TODAY))


def test_values_missing_from_the_text_layer_are_flagged(sample_truth):
    text = "Αριθμός 12.345 ... ΚΑΕΚ 999901000012/0/5 ... Α.Φ.Μ. 123456789 ... ΑΚ 000101"
    deed = {"notary": {"registry_number": "12.345"}, "property": {"kaek": "999901000012/0/5"},
            "sellers": [{"tax_id": "123456789", "id_document": "AK 000101"}]}  # Latin AK
    def not_in_text(d: dict) -> set[str]:
        return fields(i for i in validate_deed(d, TODAY, text=text) if "PDF's text" in i["message"])

    assert not_in_text(deed) == set()
    # Two swapped digits still make a 12-digit ΚΑΕΚ, so only the text can catch them
    deed["property"]["kaek"] = "999910000012/0/5"
    # A number found only inside a longer one does not count
    deed["sellers"][0]["tax_id"] = "23456789"
    assert not_in_text(deed) == {"property.kaek", "sellers[0].tax_id"}


def test_no_text_means_no_text_check(sample_truth):
    deed = copy.deepcopy(sample_truth)
    deed["property"]["kaek"] = "999910000012/0/5"
    assert not any("PDF's text" in i["message"] for i in validate_deed(deed, TODAY))
