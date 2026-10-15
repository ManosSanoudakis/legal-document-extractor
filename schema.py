"""
Output schema for deed extraction.

These Pydantic models are passed to Gemini as `response_schema`, so the model
is constrained to return exactly this shape. Every field is required but
nullable: the model must emit every key, and uses null when a value is absent.
Field descriptions are sent with the schema and act as per-field instructions.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


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
    full_name: str | None = Field(description="Full name of the attorney or legal representative")
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
    building_permit: str | None = Field(description="Building permit reference as written")


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
        description="Attorneys or representatives acting for a party. Empty list if none"
    )
    property: Property
    transaction: Transaction
    sources: list[Source] = Field(
        description="Where each value was found: one entry for every non-null field, so a person can verify it"
    )


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
