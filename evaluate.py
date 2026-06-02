from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from extractor import GeminiExtractor, SCHEMA, pdf_to_images

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field inventory — every leaf key we care about scoring
# ---------------------------------------------------------------------------

SCALAR_FIELDS = [
    "notary.name", "notary.location", "notary.registry_number",
    "property.type", "property.address", "property.municipal_unit",
    "property.floor", "property.area_sqm", "property.kaek",
    "property.building_permit",
    "transaction.deed_type", "transaction.price", "transaction.date",
]

LIST_FIELDS = ["sellers", "buyers", "legal_representatives"]
PARTY_KEYS  = ["full_name", "tax_id", "id_document", "address"]
REP_KEYS    = ["full_name", "represents", "tax_id", "id_document"]

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _scalar_completeness(result: dict) -> tuple[int, int]:
    found = total = 0
    for dotted in SCALAR_FIELDS:
        section, key = dotted.split(".")
        total += 1
        if result.get(section, {}).get(key) is not None:
            found += 1
    return found, total


def _list_completeness(result: dict) -> tuple[int, int]:
    found = total = 0
    for list_field in LIST_FIELDS:
        keys = REP_KEYS if list_field == "legal_representatives" else PARTY_KEYS
        for item in result.get(list_field) or []:
            for k in keys:
                total += 1
                if item.get(k) is not None:
                    found += 1
    return found, total


def completeness_score(result: dict) -> dict:
    s_found, s_total = _scalar_completeness(result)
    l_found, l_total = _list_completeness(result)
    total_found = s_found + l_found
    total_total = s_total + l_total
    return {
        "scalar_pct":  round(s_found / s_total * 100, 1) if s_total else 0,
        "list_pct":    round(l_found / l_total * 100, 1) if l_total else 0,
        "overall_pct": round(total_found / total_total * 100, 1) if total_total else 0,
        "filled":      total_found,
        "total":       total_total,
    }


def field_diff(a: dict, b: dict) -> list[dict]:
    """Return fields where the two results disagree (both non-null)."""
    diffs = []
    for dotted in SCALAR_FIELDS:
        section, key = dotted.split(".")
        va = (a.get(section) or {}).get(key)
        vb = (b.get(section) or {}).get(key)
        if va is not None and vb is not None and str(va) != str(vb):
            diffs.append({"field": dotted, "model_a": va, "model_b": vb})
    return diffs

# ---------------------------------------------------------------------------
# Single-run benchmark
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    model:        str
    completeness: dict
    elapsed:      float
    error:        str | None = None
    raw:          dict       = field(default_factory=dict)


def _run_once(
    image_paths: list[Path],
    api_key: str,
    model_name: str,
) -> RunResult:
    extractor = GeminiExtractor(api_key=api_key, model_name=model_name)
    try:
        result  = extractor.extract(image_paths)
        score   = completeness_score(result)
        elapsed = result.get("_meta", {}).get("elapsed_seconds", 0.0)
        return RunResult(
            model=model_name, completeness=score,
            elapsed=elapsed, raw=result,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Run failed for %s: %s", model_name, exc)
        return RunResult(
            model=model_name, completeness={},
            elapsed=0.0, error=str(exc),
        )

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_evaluation(
    pdf_path: str,
    api_key: str,
    models: list[str] | None = None,
    pages_dir: str = "pages",
) -> dict:
    """
    Run extraction with each model and return a comparison report.

    Args:
        pdf_path:  Path to the input PDF.
        api_key:   Gemini API key.
        models:    Models to benchmark (default: flash + pro).
        pages_dir: Directory for cached page images.

    Returns:
        Evaluation report dict suitable for JSON serialisation.
    """
    if models is None:
        models = GeminiExtractor.MODELS

    image_paths = pdf_to_images(pdf_path, output_dir=pages_dir)
    runs = [_run_once(image_paths, api_key, m) for m in models]

    report: dict = {
        "pdf": pdf_path,
        "models": [
            {
                "model":        r.model,
                "elapsed_s":    r.elapsed,
                "completeness": r.completeness,
                "error":        r.error,
            }
            for r in runs
        ],
    }

    if len(runs) == 2 and not any(r.error for r in runs):
        report["field_diffs"] = field_diff(runs[0].raw, runs[1].raw)
        report["winner"] = {
            "accuracy": max(
                runs, key=lambda r: r.completeness.get("overall_pct", 0)
            ).model,
            "speed": min(runs, key=lambda r: r.elapsed).model,
        }

    report["raw_results"] = {r.model: r.raw for r in runs}
    return report

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    parser = argparse.ArgumentParser(description="Benchmark Gemini models on a PDF.")
    parser.add_argument("--pdf",    default="simbolaioagorapolisiaspublic.pdf")
    parser.add_argument("--output", default="evaluation_results.json")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    report = run_evaluation(pdf_path=args.pdf, api_key=api_key)

    out = Path(args.output)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for m in report["models"]:
        print(
            f"{m['model']:30s}  "
            f"completeness={m['completeness'].get('overall_pct', 'N/A')}%  "
            f"elapsed={m['elapsed_s']:.2f}s"
        )

    if "winner" in report:
        w = report["winner"]
        print(f"\n🏆 Accuracy → {w['accuracy']}  |  ⚡ Speed → {w['speed']}")

    print(f"\nFull report saved to {out}")
