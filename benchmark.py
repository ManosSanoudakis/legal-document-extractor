"""
Measure field-level accuracy over a labelled set of deeds.

Each PDF in the dataset folder needs a JSON file of the same name holding the
correct values (generate them with samples/make_sample_deed.py --dataset N).

Usage:
    set GEMINI_API_KEY=your-key     # macOS/Linux: export GEMINI_API_KEY=your-key
    python benchmark.py                                 # all models, samples/dataset
    python benchmark.py --models gemini-3.8-flash --dataset samples/dataset
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
from collections import Counter
from pathlib import Path

from evaluate import run_evaluation
from extractor import MODELS

logger = logging.getLogger(__name__)


def load_dataset(folder: Path) -> list[tuple[Path, dict]]:
    pairs = []
    for pdf in sorted(folder.glob("*.pdf")):
        truth = pdf.with_suffix(".json")
        if truth.exists():
            pairs.append((pdf, json.loads(truth.read_text(encoding="utf-8"))))
        else:
            logger.warning("Skipping %s: no ground-truth JSON", pdf.name)
    return pairs


def summarise(per_doc: list[dict], models: list[str]) -> dict:
    """Aggregate per-document results into one row per model."""
    summary = {}
    for model in models:
        runs = [r for doc in per_doc for r in doc["models"] if r["model"] == model]
        ok = [r for r in runs if not r["error"]]
        correct = sum(r["accuracy"]["correct"] for r in ok)
        total = sum(r["accuracy"]["total"] for r in ok)
        # Which fields does this model get wrong most often? ("sellers[1].tax_id" → "sellers.tax_id")
        missed = Counter(
            m["field"].split("[")[0] + "." + m["field"].split(".")[-1] if "[" in m["field"] else m["field"]
            for r in ok for m in r["accuracy"]["mismatches"]
        )
        summary[model] = {
            "documents": len(runs),
            "failed": len(runs) - len(ok),
            "accuracy_pct": round(correct / total * 100, 1) if total else None,
            "perfect_documents": sum(1 for r in ok if r["accuracy"]["accuracy_pct"] == 100),
            "median_seconds": round(statistics.median(r["elapsed_s"] for r in ok), 2) if ok else None,
            "checks_failed": sum(r["checks_failed"] for r in ok),
            "most_missed": missed.most_common(5),
        }
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    parser = argparse.ArgumentParser(description="Field-level accuracy over a labelled dataset.")
    parser.add_argument("--dataset", default="samples/dataset", type=Path)
    parser.add_argument("--models", default=",".join(MODELS), help="Comma-separated model IDs")
    parser.add_argument("--output", default="benchmark_results.json", type=Path)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY environment variable is not set.")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    dataset = load_dataset(args.dataset)
    if not dataset:
        raise SystemExit(f"No labelled PDFs in {args.dataset}. Run: python samples/make_sample_deed.py --dataset 10")

    per_doc = []
    for i, (pdf, truth) in enumerate(dataset, start=1):
        logger.info("[%d/%d] %s", i, len(dataset), pdf.name)
        report = run_evaluation(str(pdf), api_key, models=models, truth=truth)
        report.pop("raw_results", None)
        report["pdf"] = pdf.name
        per_doc.append(report)

    summary = summarise(per_doc, models)
    args.output.write_text(
        json.dumps({"summary": summary, "documents": per_doc}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{len(dataset)} documents from {args.dataset}\n")
    print(f"{'Model':28s} {'Accuracy':>9s} {'Perfect':>8s} {'Median s':>9s} {'Failed':>7s}")
    for model, s in summary.items():
        acc = f"{s['accuracy_pct']}%" if s["accuracy_pct"] is not None else "n/a"
        print(f"{model:28s} {acc:>9s} {s['perfect_documents']:>5d}/{s['documents']:<2d} "
              f"{s['median_seconds'] or 0:>9.2f} {s['failed']:>7d}")
        if s["most_missed"]:
            print("    most missed: " + ", ".join(f"{f} ({n})" for f, n in s["most_missed"]))
    print(f"\nFull results saved to {args.output}")


if __name__ == "__main__":
    main()
