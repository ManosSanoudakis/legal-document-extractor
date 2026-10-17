"""
Output schema for deed extraction.

These Pydantic models are passed to Gemini as `response_schema`, so the model
is constrained to return exactly this shape. Every field is required but
nullable: the model must emit every key, and uses null when a value is absent.
Field descriptions are sent with the schema and act as per-field instructions.

ExtractionResult and RecheckResult, at the end, are what the pipeline returns:
the model's answer plus how it was made and what failed the checks.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DeedType(str, Enum):
    sale = "sale"
    parental_provision = "parental_provision"
    donation = "donation"
    other = "other"


class Notary(BaseModel):
    name: str | None = Field(description="Full name of the notary")
    location: str | None = Field(description="City where the notary office is located")
    registry_number: str | None = Field(description="Deed number exactly as written, e.g. 12.345")


class Party(BaseModel):
    full_name: str | None = Field(description="Full name as written, including the patronymic (του ...) if present")
    tax_id: str | None = Field(description="ΑΦΜ (Greek tax ID), digits only, no spaces")
    id_document: str | None = Field(description="ID card or passport number as written, e.g. ΑΚ 123456")
    address: str | None = Field(description="Residential address as written")


class Representative(BaseModel):
    full_name: str | None = Field(description="Full name of the person acting for the party (πληρεξούσιος)")
    represents: str | None = Field(description="Full name of the party this person represents")
    tax_id: str | None = Field(description="ΑΦΜ (Greek tax ID), digits only, no spaces")
    id_document: str | None = Field(description="ID card or passport number as written")


class Property(BaseModel):
    type: str | None = Field(description="Property type in Greek, e.g. διαμέρισμα, μονοκατοικία, κατάστημα, οικόπεδο")
    address: str | None = Field(description="Address of the property as written")
    municipal_unit: str | None = Field(description="Municipal unit (Δημοτική Ενότητα) as written")
    floor: str | None = Field(description="Floor as written, e.g. 2ος όροφος, ισόγειο")
    area_sqm: float | None = Field(description="Area in square metres as a number, e.g. 85.4")
    kaek: str | None = Field(description="ΚΑΕΚ land-registry code exactly as written, e.g. 050230600001/0/0")
    building_permit: str | None = Field(
        description="Building permit number together with the authority that issued it, as written, "
        "e.g. 512/1998 του Πολεοδομικού Γραφείου Αθηνών. Not the number alone"
    )


class Transaction(BaseModel):
    deed_type: DeedType | None = Field(
        description="sale = πώληση, parental_provision = γονική παροχή, donation = δωρεά, other = anything else"
    )
    price: float | None = Field(
        description="Agreed price (τίμημα / αντάλλαγμα) in euros as a number, e.g. 185000. "
        "Null if the deed has no price"
    )
    date: str | None = Field(description="Date the deed was signed, formatted YYYY-MM-DD")


class Source(BaseModel):
    field: str = Field(
        description='Path of the field this entry supports, e.g. "sellers[0].tax_id", "property.kaek", '
        '"transaction.price"'
    )
    page: int | None = Field(description="Page number where the value appears (the first page is 1)")
    quote: str | None = Field(
        description="Exact text copied from the document that contains the value, at most 25 words"
    )


class Deed(BaseModel):
    notary: Notary
    sellers: list[Party] = Field(description="Sellers, or the parent / donor in a parental provision or donation")
    buyers: list[Party] = Field(description="Buyers, or the child / recipient in a parental provision or donation")
    legal_representatives: list[Representative] = Field(
        description="People who sign on behalf of a party under a power of attorney (πληρεξούσιος, "
        "\"εκπροσωπείται από\"). Not the lawyers (δικηγόροι) attending the signing, the notary, engineers "
        "or earlier owners. Empty list if every party signs in person"
    )
    property: Property
    transaction: Transaction
    sources: list[Source] = Field(
        description="Where each value was found: one entry for every non-null field, so a person can verify it"
    )


SECTION_MODELS: dict[str, type[BaseModel]] = {
    "notary": Notary,
    "sellers": Party,
    "buyers": Party,
    "legal_representatives": Representative,
    "property": Property,
    "transaction": Transaction,
}


def field_description(section: str, key: str) -> str | None:
    """The schema's description of one field, e.g. ("property", "kaek"); None if no such field."""
    model = SECTION_MODELS.get(section)
    info = model.model_fields.get(key) if model else None
    return info.description if info else None


class RecheckAnswer(BaseModel):
    field: str = Field(description='The field path exactly as asked, e.g. "property.kaek"')
    value: str | None = Field(description="The value exactly as written in the document, or null if absent")
    page: int | None = Field(description="Page number where the value appears (the first page is 1)")
    quote: str | None = Field(description="Exact text copied from the document that contains the value")


class Recheck(BaseModel):
    """A second, independent reading of a few fields."""
    answers: list[RecheckAnswer]

# ---------------------------------------------------------------------------
# What the pipeline returns (not sent to the model)
# ---------------------------------------------------------------------------

class Issue(BaseModel):
    """A check the extracted data failed (see validators.py)."""
    field: str
    value: Any = None
    message: str
    severity: Literal["error", "warning"]


class Meta(BaseModel):
    model: str
    provider: str = "gemini"
    pages: int = 0
    text_layer: bool = False  # every page had text, so the values were checked against it
    elapsed_seconds: float = 0.0
    history_id: str | None = None  # set once saved, so the user's edits can be saved too
    note: str | None = None  # e.g. where a demo result came from


class ExtractionResult(BaseModel):
    """One extraction: the deed, how it was made, and what failed the checks."""
    model_config = ConfigDict(validate_assignment=True)

    # In the shape of Deed, but a plain dict: if the model's answer does not match
    # the schema, whatever JSON came back is kept rather than lost
    deed: dict[str, Any]
    meta: Meta
    validation: list[Issue] = []
    error: str | None = None  # the model's answer could not be parsed

    @classmethod
    def load(cls, data: dict, model: str = "") -> ExtractionResult:
        """Read a stored result, including ones saved before this model existed
        (the deed's keys at the top level, with _meta, _validation and _error)."""
        if "deed" in data and "meta" in data:
            return cls.model_validate(data)
        deed = {k: v for k, v in data.items() if not k.startswith("_")}
        return cls(
            deed=deed,
            meta={"model": model, **(data.get("_meta") or {})},
            validation=data.get("_validation") or [],
            error=data.get("_error"),
        )


class CheckedAnswer(RecheckAnswer):
    agrees: bool  # the same value as the first reading, ignoring formatting
    found_in_text: bool | None  # None when the PDF has no text layer


class RecheckResult(BaseModel):
    answers: list[CheckedAnswer]
    model: str
    pages: list[int]
    elapsed_seconds: float


def empty_deed() -> dict:
    """A deed with every field null and every list empty."""
    return {
        "notary": dict.fromkeys(Notary.model_fields),
        "sellers": [],
        "buyers": [],
        "legal_representatives": [],
        "property": dict.fromkeys(Property.model_fields),
        "transaction": dict.fromkeys(Transaction.model_fields),
        "sources": [],
    }
