"""
Sanity checks on extracted deed data.

The model can misread a digit or invent a value. These rules catch the cases
that can be checked without the source document: tax-ID check digits, KAEK
format, impossible dates and non-positive amounts. Each problem is reported,
never silently fixed, so a person can verify it against the PDF.
"""
from __future__ import annotations

import re
from datetime import date

KAEK_PATTERN = re.compile(r"^\d{12}(/\d+/\d+)?$")


def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value))


def afm_is_valid(afm: str) -> bool:
    """Official Greek tax-ID (ΑΦΜ) check digit."""
    if len(afm) != 9 or not afm.isdigit() or afm == "000000000":
        return False
    total = sum(int(d) * 2 ** (8 - i) for i, d in enumerate(afm[:8]))
    return total % 11 % 10 == int(afm[8])


def _issue(field: str, value: object, message: str, severity: str = "warning") -> dict:
    return {"field": field, "value": value, "message": message, "severity": severity}


def _check_tax_id(field: str, value: object) -> list[dict]:
    if value is None:
        return []
    afm = digits(value)
    if len(afm) != 9:
        return [_issue(field, value, f"ΑΦΜ should have 9 digits, found {len(afm)}.", "error")]
    if not afm_is_valid(afm):
        return [_issue(field, value, "ΑΦΜ fails the official check-digit test.", "error")]
    return []


def _check_kaek(value: object) -> list[dict]:
    if value is None:
        return []
    compact = re.sub(r"\s", "", str(value))
    if not KAEK_PATTERN.match(compact):
        return [_issue("property.kaek", value, "ΚΑΕΚ should be 12 digits, optionally followed by /building/unit.")]
    return []


def _check_date(value: object, today: date) -> list[dict]:
    if value is None:
        return []
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return [_issue("transaction.date", value, "Date is not a valid YYYY-MM-DD date.", "error")]
    if parsed > today:
        return [_issue("transaction.date", value, "Date is in the future.", "error")]
    if parsed.year < 1900:
        return [_issue("transaction.date", value, "Date is before 1900.")]
    return []


def _check_positive(field: str, value: object, upper: float) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return [_issue(field, value, "Expected a number.", "error")]
    if value <= 0:
        return [_issue(field, value, "Must be greater than zero.", "error")]
    if value > upper:
        return [_issue(field, value, f"Unusually large (over {upper:,.0f}).")]
    return []


def validate_deed(data: dict, today: date | None = None) -> list[dict]:
    """Return a list of issues found in an extracted deed. Empty means all checks passed."""
    today = today or date.today()
    issues: list[dict] = []

    parties = [
        (role, i, p)
        for role in ("sellers", "buyers", "legal_representatives")
        for i, p in enumerate(data.get(role) or [])
    ]
    for role, i, p in parties:
        issues += _check_tax_id(f"{role}[{i}].tax_id", p.get("tax_id"))

    prop = data.get("property") or {}
    txn = data.get("transaction") or {}
    issues += _check_kaek(prop.get("kaek"))
    issues += _check_date(txn.get("date"), today)
    issues += _check_positive("property.area_sqm", prop.get("area_sqm"), upper=100_000)
    issues += _check_positive("transaction.price", txn.get("price"), upper=100_000_000)

    if not data.get("sellers"):
        issues.append(_issue("sellers", None, "No sellers found."))
    if not data.get("buyers"):
        issues.append(_issue("buyers", None, "No buyers found."))

    # The same person cannot be on both sides of the deed
    seller_ids = {digits(p["tax_id"]) for p in data.get("sellers") or [] if p.get("tax_id")}
    for i, p in enumerate(data.get("buyers") or []):
        if p.get("tax_id") and digits(p["tax_id"]) in seller_ids:
            issues.append(_issue(f"buyers[{i}].tax_id", p["tax_id"], "Same ΑΦΜ appears as a seller.", "error"))

    return issues
