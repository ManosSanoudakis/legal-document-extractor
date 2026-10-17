"""
Field-level accuracy against a ground-truth deed.

Every field in the ground truth is scored, including fields that are null:
a model that invents a value where the deed has none is marked wrong. This is
what separates accuracy from completeness, which rewards any non-null value.

Comparison is tolerant of formatting only: accents, case, spacing and
punctuation are ignored, ID numbers may use Latin look-alike letters, a
name with or without the patronymic counts as the same name, and a municipal
unit with or without the "Δημοτική Ενότητα" label counts as the same unit.
Other text must match in full: an address without its city is wrong.

An invented party (say, a lawyer listed as a legal representative) counts
as wrong in every one of its fields, just as a missed party does.
"""
from __future__ import annotations

import re
from datetime import date

from validators import LOOKALIKES, digits, norm_text

SCALAR_FIELDS: dict[str, str] = {
    "notary.name": "name",
    "notary.location": "name",  # "Πειραιάς" or "Πειραιά" as written in "στον Πειραιά"
    "notary.registry_number": "digits",
    "property.type": "text",
    "property.address": "text",
    "property.municipal_unit": "unit",
    "property.floor": "floor",
    "property.area_sqm": "number",
    "property.kaek": "digits",
    "property.building_permit": "permit",
    "transaction.deed_type": "exact",
    "transaction.price": "number",
    "transaction.date": "date",
}

PARTY_FIELDS = {"full_name": "name", "tax_id": "digits", "id_document": "id", "address": "text"}
REP_FIELDS = {"full_name": "name", "represents": "name", "tax_id": "digits", "id_document": "id"}

# "Δημοτική Ενότητα Ζωγράφου" and "Ζωγράφου" name the same unit
_UNIT_LABEL = re.compile(r"^(δημοτικη ενοτητα|δ ε) ")
# "υπ' αριθμ. 1234/2005 του Πολεοδομικού Γραφείου άδειας" is the permit copied with its sentence
_PERMIT_WORDS = re.compile(r"^(υπ αριθμ|αριθμ|αρ) | αδεια[σς]?$")  # casefold() turns final ς into σ


def _to_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = re.sub(r"[^\d.,-]", "", str(value))
    if "," in text:  # Greek format: 185.000,50
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _to_date(value: object) -> date | None:
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return None
    return None


def values_match(kind: str, expected: object, got: object) -> bool:
    """Compare one field. Both null is a match; exactly one null is not."""
    if expected is None or got is None:
        return expected is None and got is None

    if kind == "digits":
        return digits(expected) == digits(got) != ""
    if kind == "number":
        a, b = _to_number(expected), _to_number(got)
        return a is not None and b is not None and abs(a - b) < 0.01
    if kind == "date":
        a, b = _to_date(expected), _to_date(got)
        return a is not None and a == b
    if kind == "exact":
        return str(expected) == str(got)
    if kind == "id":
        def clean(v: object) -> str:
            return re.sub(r"\s", "", str(v)).upper().translate(LOOKALIKES)
        return clean(expected) == clean(got)
    if kind == "floor":
        da, db = digits(expected), digits(got)
        if da or db:
            return da == db
        # fall through to text comparison for e.g. "ισόγειο"

    a, b = norm_text(expected), norm_text(got)
    if kind == "unit":
        a, b = _UNIT_LABEL.sub("", a), _UNIT_LABEL.sub("", b)
    if kind == "permit":
        a, b = _PERMIT_WORDS.sub("", a), _PERMIT_WORDS.sub("", b)
    if a == b:
        return True
    if kind != "name":
        return False
    shorter, longer = sorted((a, b), key=len)
    # "Γεώργιος Υποθετικός" vs "Γεώργιος Υποθετικός του Νικολάου"
    return len(shorter) >= 4 and longer.startswith(shorter)


def _get(data: dict, dotted: str) -> object:
    section, key = dotted.split(".")
    value = (data.get(section) or {}).get(key)
    return value.value if hasattr(value, "value") else value  # Enum → str


def _match_parties(expected: list[dict], got: list[dict]) -> list[tuple[dict, dict | None]]:
    """Pair each expected party with the predicted party that is the same person."""
    remaining = list(got)
    pairs = []
    for exp in expected:
        match = next(
            (g for g in remaining if exp.get("tax_id") and values_match("digits", exp["tax_id"], g.get("tax_id"))),
            None,
        ) or next(
            (g for g in remaining if values_match("name", exp.get("full_name"), g.get("full_name"))),
            None,
        )
        if match is not None:
            remaining.remove(match)
        pairs.append((exp, match))
    return pairs


def score_accuracy(predicted: dict, truth: dict) -> dict:
    """Score a predicted deed against the ground truth, field by field."""
    correct = total = 0
    mismatches: list[dict] = []

    def record(field: str, kind: str, expected: object, got: object) -> None:
        nonlocal correct, total
        total += 1
        if values_match(kind, expected, got):
            correct += 1
        else:
            mismatches.append({"field": field, "expected": expected, "got": got})

    for dotted, kind in SCALAR_FIELDS.items():
        record(dotted, kind, _get(truth, dotted), _get(predicted, dotted))

    extra = 0
    for role, fields in (("sellers", PARTY_FIELDS), ("buyers", PARTY_FIELDS), ("legal_representatives", REP_FIELDS)):
        expected_list = truth.get(role) or []
        got_list = [p for p in predicted.get(role) or [] if any(v is not None for v in p.values())]
        pairs = _match_parties(expected_list, got_list)
        for i, (exp, got) in enumerate(pairs):
            for key, kind in fields.items():
                record(f"{role}[{i}].{key}", kind, exp.get(key), (got or {}).get(key))
        matched = [g for _, g in pairs if g is not None]
        invented = [g for g in got_list if not any(g is m for m in matched)]
        for i, got in enumerate(invented, start=len(pairs)):
            for key in fields:
                total += 1
                mismatches.append({"field": f"{role}[{i}].{key}", "expected": None, "got": got.get(key)})
        extra += len(invented)

    return {
        "accuracy_pct": round(correct / total * 100, 1) if total else 0.0,
        "correct": correct,
        "total": total,
        "extra_parties": extra,
        "mismatches": mismatches,
    }
