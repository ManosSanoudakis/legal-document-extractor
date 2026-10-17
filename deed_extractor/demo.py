"""
Demo deeds: saved model answers that anyone can open without an API key.

Each demo in samples/demo/ is a fictional deed (<id>.pdf), a real answer
Gemini gave for it in a benchmark run (<id>.json, an ExtractionResult), and
its correct values (<id>.truth.json), so a model evaluation of it can measure
accuracy. demo.json lists them in order with a title and a description.
Build them with scripts/build_demo.py.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from .schema import ExtractionResult

DEMO_DIR = Path(__file__).resolve().parent.parent / "samples" / "demo"


@cache
def demos() -> list[dict]:
    """[{id, title, description}], or [] when there are none."""
    manifest = DEMO_DIR / "demo.json"
    if not manifest.exists():
        return []
    items = json.loads(manifest.read_text(encoding="utf-8"))
    return [d for d in items if (DEMO_DIR / f"{d['id']}.pdf").exists() and (DEMO_DIR / f"{d['id']}.json").exists()]


def _known(demo_id: str) -> bool:
    return any(d["id"] == demo_id for d in demos())


def pdf_path(demo_id: str) -> Path | None:
    return DEMO_DIR / f"{demo_id}.pdf" if _known(demo_id) else None


def result(demo_id: str) -> ExtractionResult | None:
    if not _known(demo_id):
        return None
    return ExtractionResult.model_validate_json((DEMO_DIR / f"{demo_id}.json").read_text(encoding="utf-8"))


def truth(demo_id: str) -> dict | None:
    path = DEMO_DIR / f"{demo_id}.truth.json"
    return json.loads(path.read_text(encoding="utf-8")) if _known(demo_id) and path.exists() else None
