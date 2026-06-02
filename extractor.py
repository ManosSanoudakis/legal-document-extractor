from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

import fitz
from google import genai
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema & Prompt
# ---------------------------------------------------------------------------

SCHEMA: dict = {
    "notary": {"name": None, "location": None, "registry_number": None},
    "sellers": [
        {"full_name": None, "tax_id": None, "id_document": None, "address": None}
    ],
    "buyers": [
        {"full_name": None, "tax_id": None, "id_document": None, "address": None}
    ],
    "legal_representatives": [
        {"full_name": None, "represents": None, "tax_id": None, "id_document": None}
    ],
    "property": {
        "type": None, "address": None, "municipal_unit": None,
        "floor": None, "area_sqm": None, "kaek": None, "building_permit": None,
    },
    "transaction": {"deed_type": None, "price": None, "date": None},
}

PROMPT = f"""
Είσαι ειδικός στην ανάλυση ελληνικών νοταριακών εγγράφων.

Εξάγαγε τα παρακάτω στοιχεία από τις σελίδες του συμβολαίου.
Επίστρεψε ΜΟΝΟ ένα έγκυρο JSON object — χωρίς εξήγηση,
χωρίς markdown backticks, χωρίς πρόλογο.

Κανόνες:
- Αν ένα πεδίο δεν βρεθεί, άφησέ το null.
- Αν υπάρχουν πολλοί πωλητές ή αγοραστές, βάλε ΟΛΑ στις λίστες.
- Σε γονική παροχή: πωλητής = γονέας, αγοραστής = παιδί.
- Το KAEK είναι μακρύς αριθμός (π.χ. 05 23 06 00 00 01234/0/0).
- Η τιμή μπορεί να αναφέρεται ως "τίμημα" ή "αντάλλαγμα".
- area_sqm πρέπει να είναι αριθμός (float), όχι string.

Schema:
{json.dumps(SCHEMA, ensure_ascii=False, indent=2)}
"""

# ---------------------------------------------------------------------------
# PDF → images
# ---------------------------------------------------------------------------

def pdf_to_images(
    pdf_path: str,
    output_dir: str = "pages",
    dpi: int = 150,
) -> list[Path]:
    """Rasterise every PDF page to JPEG; cache results on disk."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(path))

    paths: list[Path] = []
    for i, page in enumerate(doc, start=1):
        dest = out / f"{i}.jpeg"
        if not dest.exists():
            page.get_pixmap(dpi=dpi).save(str(dest))
        paths.append(dest)

    logger.info("%d page(s) ready in '%s/'", len(paths), out)
    return paths

# ---------------------------------------------------------------------------
# Extractor base
# ---------------------------------------------------------------------------

class BaseExtractor(ABC):
    """Common interface for VLM extraction backends."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    def extract(self, image_paths: list[Path]) -> dict: ...

    @staticmethod
    def _parse_response(text: str) -> dict:
        clean = (
            text.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        try:
            return json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error: %s", exc)
            return {**SCHEMA, "_error": str(exc)}

    def _meta(self, elapsed: float, pages: int) -> dict:
        return {
            "model": self.model_name,
            "provider": self.__class__.__name__.replace("Extractor", "").lower(),
            "pages": pages,
            "elapsed_seconds": round(elapsed, 2),
        }

# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

class GeminiExtractor(BaseExtractor):
    """Google Gemini Vision extraction backend."""

    MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

    def extract(self, image_paths: list[Path]) -> dict:
        client = genai.Client(api_key=self.api_key)
        images = [Image.open(p) for p in image_paths]

        t0 = time.perf_counter()
        response = client.models.generate_content(
            model=self.model_name,
            contents=[*images, PROMPT],
        )
        elapsed = time.perf_counter() - t0
        logger.info(
            "Gemini response in %.2fs — model=%s pages=%d",
            elapsed, self.model_name, len(images),
        )

        data = self._parse_response(response.text)
        data["_meta"] = self._meta(elapsed, len(images))
        return data

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _get_extractor(model_name: str, api_key: str) -> BaseExtractor:
    if model_name.startswith("gemini"):
        return GeminiExtractor(api_key=api_key, model_name=model_name)
    raise ValueError(f"Unsupported model: '{model_name}'")


def run_pipeline(
    pdf_path: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash",
    pages_dir: str = "pages",
) -> dict:
    """PDF → page images → VLM extraction → structured dict."""
    image_paths = pdf_to_images(pdf_path, output_dir=pages_dir)
    return _get_extractor(model_name, api_key).extract(image_paths)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    result = run_pipeline(pdf_path="simbolaioagorapolisiaspublic.pdf", api_key=api_key)

    output = Path("extracted_data.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.read_text(encoding="utf-8"))
