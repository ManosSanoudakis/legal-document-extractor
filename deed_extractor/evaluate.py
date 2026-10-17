from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .accuracy import score_accuracy
from .extractor import GeminiExtractor, pdf_page_texts, pdf_to_images
from .schema import ExtractionResult

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
    result:       ExtractionResult | None = None
    accuracy:     dict | None = None
    exception:    Exception | None = None

    @property
    def deed(self) -> dict:
        return self.result.deed if self.result else {}


def _run_once(
    image_paths: list[Path],
    page_texts: list[str],
    api_key: str,
    model_name: str,
) -> RunResult:
    extractor = GeminiExtractor(api_key=api_key, model_name=model_name)
    try:
        result = extractor.extract(image_paths, page_texts)
        return RunResult(
            model=model_name, completeness=completeness_score(result.deed),
            elapsed=result.meta.elapsed_seconds, result=result,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Run failed for %s: %s", model_name, exc)
        return RunResult(
            model=model_name, completeness={},
            elapsed=0.0, error=str(exc), exception=exc,
        )

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_evaluation(
    pdf_path: str,
    api_key: str,
    models: list[str] | None = None,
    truth: dict | None = None,
    on_stage: Callable[[str], None] | None = None,
    raise_if_all_failed: bool = False,
) -> dict:
    """
    Run extraction with each model and return a comparison report.

    Page images are written to a temporary directory that is deleted
    once all models have run.

    Args:
        pdf_path:  Path to the input PDF.
        api_key:   Gemini API key.
        models:    Models to benchmark (default: GeminiExtractor.MODELS).
        truth:     Ground-truth deed. When given, each model is also scored
                   on field-level accuracy, which decides the winner.
        on_stage:  Told "reading" and then "extracting", for progress reporting.
        raise_if_all_failed: Re-raise the first error if no model succeeded
                   (e.g. a rejected key), instead of reporting it per model.

    Returns:
        Evaluation report dict suitable for JSON serialisation.
    """
    if models is None:
        models = GeminiExtractor.MODELS
    report_stage = on_stage or (lambda stage: None)

    with tempfile.TemporaryDirectory() as pages_dir:
        report_stage("reading")
        image_paths = pdf_to_images(pdf_path, output_dir=pages_dir)
        page_texts = pdf_page_texts(pdf_path)
        report_stage("extracting")
        # Models run in parallel: total time is the slowest model, not the sum
        with ThreadPoolExecutor(max_workers=len(models)) as pool:
            runs = list(pool.map(lambda m: _run_once(image_paths, page_texts, api_key, m), models))

    if raise_if_all_failed and runs and all(r.exception for r in runs):
        raise runs[0].exception

    if truth is not None:
        for r in runs:
            if not r.error:
                r.accuracy = score_accuracy(r.deed, truth)

    report: dict = {
        "pdf": pdf_path,
        "models": [
            {
                "model":        r.model,
                "elapsed_s":    r.elapsed,
                "completeness": r.completeness,
                "accuracy":     r.accuracy,
                "checks_failed": len(r.result.validation) if r.result else 0,
                "error":        r.error,
            }
            for r in runs
        ],
    }

    if len(runs) == 2 and not any(r.error for r in runs):
        report["field_diffs"] = field_diff(runs[0].deed, runs[1].deed)
        if truth is not None:
            score = lambda r: r.accuracy["accuracy_pct"]  # noqa: E731
        else:
            score = lambda r: r.completeness.get("overall_pct", 0)  # noqa: E731
        fastest = min(runs, key=lambda r: r.elapsed)
        tie = score(runs[0]) == score(runs[1])
        report["winner"] = {
            # On a tie the faster model wins, not whichever happens to be listed first
            "accuracy": fastest.model if tie else max(runs, key=score).model,
            "basis": "accuracy" if truth is not None else "completeness",
            "tie": tie,
            "speed": fastest.model,
        }

    # Each model's full answer, so a change to the scoring can be re-applied later
    report["raw_results"] = {r.model: r.result.model_dump(mode="json") if r.result else None for r in runs}
    return report

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    parser = argparse.ArgumentParser(description="Benchmark Gemini models on a PDF.")
    parser.add_argument("--pdf",    required=True)
    parser.add_argument("--truth",  help="Ground-truth JSON for field-level accuracy")
    parser.add_argument("--output", default="evaluation_results.json")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    truth = json.loads(Path(args.truth).read_text(encoding="utf-8")) if args.truth else None
    report = run_evaluation(pdf_path=args.pdf, api_key=api_key, truth=truth)

    out = Path(args.output)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for m in report["models"]:
        print(
            f"{m['model']:30s}  "
            f"completeness={m['completeness'].get('overall_pct', 'N/A')}%  "
            + (f"accuracy={m['accuracy']['accuracy_pct']}%  " if m["accuracy"] else "")
            + f"elapsed={m['elapsed_s']:.2f}s"
        )

    if "winner" in report:
        w = report["winner"]
        best = f"tie (faster: {w['accuracy']})" if w["tie"] else w["accuracy"]
        print(f"\nMost {w['basis']}: {best}  |  Fastest: {w['speed']}")

    print(f"\nFull report saved to {out}")
