import copy
from datetime import date

from conftest import make_valid_afm
from validators import afm_is_valid, validate_deed

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
    assert {"sellers[0].tax_id", "sellers[1].tax_id", "buyers[0].tax_id", "legal_representatives[0].tax_id"} <= fields(issues)
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


def test_missing_parties_and_same_person_both_sides(sample_truth):
    deed = clean_deed(sample_truth)
    deed["buyers"][0]["tax_id"] = deed["sellers"][0]["tax_id"]
    assert "buyers[0].tax_id" in fields(validate_deed(deed, today=TODAY))
    deed["sellers"] = []
    assert "sellers" in fields(validate_deed(deed, today=TODAY))
