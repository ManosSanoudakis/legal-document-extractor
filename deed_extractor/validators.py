"""
Sanity checks on extracted deed data.

The model can misread a digit or invent a value. These rules catch the cases
that can be checked without the source document: tax-ID check digits, KAEK
format, impossible dates and non-positive amounts. When the PDF has a text
layer, copied values are also looked up in it, which catches a misread digit
that still looks valid. Each problem is reported, never silently fixed, so a
person can verify it against the PDF.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

KAEK_PATTERN = re.compile(r"^\d{12}(/\d+/\d+)?$")
PATH_PATTERN = re.compile(r"^(\w+)(?:\[(\d+)\])?\.(\w+)$")

# Fields whose value is copied from the document as written, so it should
# appear in the quoted source. Numbers, dates and deed type are converted.
DIGIT_FIELDS = {"tax_id", "kaek", "registry_number"}
COPIED_FIELDS = DIGIT_FIELDS | {"full_name", "id_document", "address", "name", "location", "municipal_unit"}

# Greek capitals that look identical to Latin ones (ID numbers are often typed either way)
LOOKALIKES = str.maketrans("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "ABEZHIKMNOPTYX")

# Values looked up in the PDF's text layer. Location and municipal unit are left
# out: they are often written in another grammatical case ("στον Πειραιά").
TEXT_CHECKED = {
    "notary": ("name", "registry_number"),
    "property": ("address", "kaek"),
    "sellers": ("full_name", "tax_id", "id_document", "address"),
    "buyers": ("full_name", "tax_id", "id_document", "address"),
    "legal_representatives": ("full_name", "tax_id", "id_document"),
}


def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value))


def norm_text(value: object) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def get_path(data: dict, path: str) -> object:
    """Read a value by path: "property.kaek" or "sellers[0].tax_id". Missing → None."""
    m = PATH_PATTERN.match(path)
    if not m:
        return None
    section, index, key = m.groups()
    node = data.get(section)
    if index is not None:
        items = node or []
        node = items[int(index)] if int(index) < len(items) else None
    return node.get(key) if isinstance(node, dict) else None


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


def _check_sources(data: dict) -> list[dict]:
    """Flag copied values that do not appear in the text the model quoted for them."""
    issues = []
    for source in data.get("sources") or []:
        path, quote = source.get("field") or "", source.get("quote")
        key = path.rsplit(".", 1)[-1]
        value = get_path(data, path)
        if key not in COPIED_FIELDS or value is None or not quote:
            continue
        if key in DIGIT_FIELDS:
            found = digits(value) != "" and digits(value) in digits(quote)
        else:
            found = norm_text(value) in norm_text(quote)
        if not found:
            issues.append(_issue(path, value, "Value does not appear in the quoted source text."))
    return issues


def _number_key(value: object) -> str:
    """Join digits split by a space or dot ("12.345" → "12345"), keep other separators ("/0/5")."""
    return re.sub(r"(?<=\d)[\s.](?=\d)", "", str(value).strip())


def in_text(key: str, value: object, text: str) -> bool:
    """Does a copied value appear in the PDF's text layer?"""
    if key in DIGIT_FIELDS:
        needle = _number_key(value)
        # Whole numbers only: 123456789 must not match inside 9123456789
        return bool(needle) and re.search(rf"(?<!\d){re.escape(needle)}(?!\d)", _number_key(text)) is not None
    if key == "id_document":
        def compact(v: object) -> str:
            return re.sub(r"\s", "", str(v)).upper().translate(LOOKALIKES)
        return compact(value) in compact(text)
    return norm_text(value) in norm_text(text)


def values_agree(key: str, a: object, b: object) -> bool:
    """Do two readings of the same field say the same thing, ignoring formatting?"""
    if a is None or b is None:
        return a is None and b is None
    if key in DIGIT_FIELDS:
        return _number_key(a) == _number_key(b)
    if key == "id_document":
        return re.sub(r"\s", "", str(a)).upper().translate(LOOKALIKES) == \
            re.sub(r"\s", "", str(b)).upper().translate(LOOKALIKES)
    if key in ("area_sqm", "price"):
        def number(v: object) -> str:
            s = re.sub(r"[^\d,.]", "", str(v))
            return s.replace(".", "").replace(",", ".") if "," in s else s
        try:
            return abs(float(number(a)) - float(number(b))) < 0.01
        except ValueError:
            return False
    return norm_text(a) == norm_text(b)


def _check_in_text(data: dict, text: str) -> list[dict]:
    """Flag copied values that appear nowhere in the PDF's text layer."""
    issues = []
    for section, keys in TEXT_CHECKED.items():
        node = data.get(section)
        entries = [(f"{section}[{i}]", p) for i, p in enumerate(node or [])] if isinstance(node, list) \
            else [(section, node or {})]
        for prefix, entry in entries:
            for key in keys:
                value = entry.get(key)
                if value is not None and str(value).strip() and not in_text(key, value, text):
                    issues.append(_issue(f"{prefix}.{key}", value, "Not found in the PDF's text: check it on the page.",
                                         "error"))
    return issues


def validate_deed(data: dict, today: date | None = None, text: str | None = None) -> list[dict]:
    """Return a list of issues found in an extracted deed. Empty means all checks passed.

    text is the PDF's text layer, when every page has one; copied values are then
    also looked up in it.
    """
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

    issues += _check_sources(data)
    if text:
        issues += _check_in_text(data, text)
    return issues
