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

# Gemini often answers 429 (busy) or 5xx under load; these usually succeed on
# a retry. Up to 3 attempts with exponential backoff, each capped at 150 s.
HTTP_OPTIONS = types.HttpOptions(
    timeout=150_000,
    retry_options=types.HttpRetryOptions(
        attempts=3,
        initial_delay=2.0,
        max_delay=20.0,
        http_status_codes=[429, 500, 502, 503, 504],
    ),
)

# First model is the default. Both defaults are on Gemini's free tier (Pro has
# no free quota). Override with a comma-separated GEMINI_MODELS env var, e.g.
# to compare against Pro on a paid key, or when Google retires a model.
DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
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
- Στο legal_representatives βάλε μόνο όποιον εκπροσωπεί συμβαλλόμενο με
  πληρεξούσιο ("εκπροσωπείται από"). Οι δικηγόροι που παρίστανται στην
  υπογραφή, ο συμβολαιογράφος, οι μηχανικοί και οι προηγούμενοι ιδιοκτήτες
  δεν είναι εκπρόσωποι.
- Η τιμή μπορεί να αναφέρεται ως "τίμημα" ή "αντάλλαγμα".
- Μετάτρεψε την ημερομηνία υπογραφής σε μορφή YYYY-MM-DD.
- Όπου δίνεται το κείμενο μιας σελίδας, αντέγραψε αριθμούς και ονόματα από
  αυτό και όχι από την εικόνα: είναι το ακριβές κείμενο του PDF.
- Για κάθε πεδίο που συμπλήρωσες, πρόσθεσε στο sources τη σελίδα και το
  ακριβές απόσπασμα του εγγράφου όπου εμφανίζεται η τιμή.
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


# A page with less text than this is treated as scanned (a watermark alone is not a text layer)
MIN_PAGE_TEXT = 50


def pdf_page_texts(pdf_path: str) -> list[str]:
    """The text layer of each page, whitespace collapsed; "" for a scanned page.

    A digital PDF carries its exact characters, so numbers read from the text
    cannot be misread the way they can from a page image.
    """
    with fitz.open(pdf_path) as doc:
        texts = [" ".join(page.get_text().split()) for page in doc]
    return [t if len(t) >= MIN_PAGE_TEXT else "" for t in texts]

# ---------------------------------------------------------------------------
# Extractor base
# ---------------------------------------------------------------------------

class BaseExtractor(ABC):
    """Common interface for VLM extraction backends."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    def extract(self, image_paths: list[Path], page_texts: list[str] | None = None) -> dict: ...

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

    def _meta(self, elapsed: float, pages: int, text_layer: bool) -> dict:
        return {
            "model": self.model_name,
            "provider": self.__class__.__name__.replace("Extractor", "").lower(),
            "pages": pages,
            "text_layer": text_layer,
            "elapsed_seconds": round(elapsed, 2),
        }

# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

class GeminiExtractor(BaseExtractor):
    """Google Gemini Vision extraction backend."""

    MODELS = MODELS

    def extract(self, image_paths: list[Path], page_texts: list[str] | None = None) -> dict:
        client = genai.Client(api_key=self.api_key, http_options=HTTP_OPTIONS)
        images = [Image.open(p) for p in image_paths]
        texts = page_texts or [""] * len(images)

        # Label each page so the model can cite page numbers in `sources`. A page
        # with a text layer also gets its text: exact characters for numbers and
        # names, while the image still shows the layout.
        contents: list = []
        for i, (img, text) in enumerate(zip(images, texts, strict=True), start=1):
            contents += [f"Σελίδα {i}:", img]
            if text:
                contents.append(f"Κείμενο σελίδας {i} (από το PDF):\n{text}")
        contents.append(PROMPT)

        try:
            t0 = time.perf_counter()
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents,
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

        # Values can be checked against the text only if every page has one;
        # otherwise a value from a scanned page would be flagged as missing
        full_text = " ".join(texts) if all(texts) else None
        data = self._structured(response)
        data["_validation"] = validate_deed(data, text=full_text)
        data["_meta"] = self._meta(elapsed, len(images), text_layer=full_text is not None)
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
    """PDF → page images (+ text layer) → VLM extraction → structured dict.

    Page images are written to a temporary directory that is deleted
    afterwards, so no document data is left on disk.
    """
    with tempfile.TemporaryDirectory() as pages_dir:
        image_paths = pdf_to_images(pdf_path, output_dir=pages_dir)
        return _get_extractor(model_name, api_key).extract(image_paths, pdf_page_texts(pdf_path))

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
