"""
Export an extracted (and possibly hand-corrected) deed to CSV or Excel.

CSV is one flat table of field / value rows. Excel has two sheets: the deed
details, and one row per person with their role.
"""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font

DETAIL_FIELDS = [
    ("Notary", "notary", "name", "Name"),
    ("Notary", "notary", "location", "Location"),
    ("Notary", "notary", "registry_number", "Registry number"),
    ("Property", "property", "type", "Type"),
    ("Property", "property", "address", "Address"),
    ("Property", "property", "municipal_unit", "Municipal unit"),
    ("Property", "property", "floor", "Floor"),
    ("Property", "property", "area_sqm", "Area (m²)"),
    ("Property", "property", "kaek", "ΚΑΕΚ"),
    ("Property", "property", "building_permit", "Building permit"),
    ("Transaction", "transaction", "deed_type", "Deed type"),
    ("Transaction", "transaction", "price", "Price (EUR)"),
    ("Transaction", "transaction", "date", "Date"),
]
ROLES = [("sellers", "Seller"), ("buyers", "Buyer"), ("legal_representatives", "Representative")]
PEOPLE_COLUMNS = ["Role", "Name", "Tax ID (ΑΦΜ)", "ID document", "Address", "Represents"]


def detail_rows(deed: dict) -> list[list]:
    return [
        [section, label, (deed.get(key) or {}).get(field)]
        for section, key, field, label in DETAIL_FIELDS
    ]


def people_rows(deed: dict) -> list[list]:
    return [
        [role, p.get("full_name"), p.get("tax_id"), p.get("id_document"), p.get("address"), p.get("represents")]
        for key, role in ROLES
        for p in deed.get(key) or []
    ]


def to_csv(deed: dict) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Section", "Field", "Value"])
    writer.writerows(detail_rows(deed))
    for key, role in ROLES:
        for i, p in enumerate(deed.get(key) or [], start=1):
            for field, value in p.items():
                writer.writerow([f"{role} {i}", field, value])
    # BOM so Excel opens the Greek text as UTF-8
    return ("﻿" + out.getvalue()).encode("utf-8")


def to_xlsx(deed: dict) -> bytes:
    wb = Workbook()
    details = wb.active
    details.title = "Deed"
    details.append(["Section", "Field", "Value"])
    for row in detail_rows(deed):
        details.append(row)

    people = wb.create_sheet("People")
    people.append(PEOPLE_COLUMNS)
    for row in people_rows(deed):
        people.append(row)

    for sheet, widths in ((details, [14, 18, 60]), (people, [16, 40, 16, 16, 45, 40])):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for col, width in zip("ABCDEF", widths, strict=False):  # fewer widths than letters is fine
            sheet.column_dimensions[col].width = width
        sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
