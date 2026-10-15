from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path

import fitz
from google import genai
from google.genai import types
from PIL import Image
from pydantic import ValidationError

from schema import Deed, empty_deed
from validators import validate_deed

logger = logging.getLogger(__name__)

# Caps response size (and cost). Gemini counts "thinking" tokens here too,
# so this is set well above the ~1-2k tokens the JSON itself needs.
MAX_OUTPUT_TOKENS = 16_384

# First model is the default. Override with a comma-separated GEMINI_MODELS
# env var when Google retires or renames models.
DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-3.1-pro-preview"]
MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()] or DEFAULT_MODELS

# ---------------------------------------------------------------------------
# Prompt (the output shape is enforced separately by schema.Deed)
# ---------------------------------------------------------------------------

PROMPT = """
Είσαι ειδικός στην ανάλυση ελληνικών συμβολαιογραφικών εγγράφων.

Εξάγαγε τα στοιχεία του συμβολαίου από τις σελίδες που ακολουθούν,
σύμφωνα με το schema της απάντησης.

Κανόνες:
- Αν ένα πεδίο δεν αναγράφεται στο έγγραφο, βάλε null. Μην μαντεύεις.
- Αντέγραψε αριθμούς (ΑΦΜ, ΚΑΕΚ, ταυτότητες) ακριβώς όπως γράφονται.
- Αν υπάρχουν πολλοί πωλητές ή αγοραστές, βάλε ΟΛΟΥΣ στις λίστες.
- Σε γονική παροχή ή δωρεά: πωλητής = γονέας / δωρητής, αγοραστής = τέκνο / δωρεοδόχος.
- Η τιμή μπορεί να αναφέρεται ως "τίμημα" ή "αντάλλαγμα".
- Μετάτρεψε την ημερομηνία υπογραφής σε μορφή YYYY-MM-DD.
"""

# ---------------------------------------------------------------------------
# PDF → images
# ---------------------------------------------------------------------------

def pdf_to_images(
    pdf_path: str,
    output_dir: str,
    dpi: int = 150,
) -> list[Path]:
    """Rasterise every PDF page to JPEG in output_dir."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc, start=1):
            dest = out / f"{i}.jpeg"
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
    def _parse_response(text: str | None) -> dict:
        # text is None when the model returns no content (e.g. hit the token cap)
        clean = (
            (text or "").strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        try:
            return json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error: %s", exc)
            return {**empty_deed(), "_error": str(exc)}

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

    MODELS = MODELS

    def extract(self, image_paths: list[Path]) -> dict:
        client = genai.Client(api_key=self.api_key)
        images = [Image.open(p) for p in image_paths]

        try:
            t0 = time.perf_counter()
            response = client.models.generate_content(
                model=self.model_name,
                contents=[*images, PROMPT],
                config=types.GenerateContentConfig(
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    response_mime_type="application/json",
                    response_schema=Deed,
                ),
            )
            elapsed = time.perf_counter() - t0
        finally:
            # Release file handles so the page images can be deleted
            for img in images:
                img.close()
        logger.info(
            "Gemini response in %.2fs — model=%s pages=%d",
            elapsed, self.model_name, len(images),
        )

        data = self._structured(response)
        data["_validation"] = validate_deed(data)
        data["_meta"] = self._meta(elapsed, len(images))
        return data

    def _structured(self, response: types.GenerateContentResponse) -> dict:
        """Schema-validated output, falling back to plain JSON parsing."""
        if isinstance(response.parsed, Deed):
            return response.parsed.model_dump(mode="json")
        try:
            return Deed.model_validate_json(response.text or "").model_dump(mode="json")
        except ValidationError:
            # Schema-constrained output should always validate; keep whatever
            # JSON came back rather than losing it, and flag the problem.
            logger.warning("Response did not match the schema; parsing as plain JSON")
            return self._parse_response(response.text)

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
    model_name: str = MODELS[0],
) -> dict:
    """PDF → page images → VLM extraction → structured dict.

    Page images are written to a temporary directory that is deleted
    afterwards, so no document data is left on disk.
    """
    with tempfile.TemporaryDirectory() as pages_dir:
        image_paths = pdf_to_images(pdf_path, output_dir=pages_dir)
        return _get_extractor(model_name, api_key).extract(image_paths)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    parser = argparse.ArgumentParser(description="Extract structured data from a notarial deed PDF.")
    parser.add_argument("--pdf",    required=True,                  help="Path to the input PDF")
    parser.add_argument("--output", default="extracted_data.json",  help="Output JSON path")
    parser.add_argument("--model",  default=MODELS[0],              choices=MODELS)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    result = run_pipeline(pdf_path=args.pdf, api_key=api_key, model_name=args.model)

    output = Path(args.output)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.read_text(encoding="utf-8"))
