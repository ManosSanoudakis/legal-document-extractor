"""
Build the demo deeds in samples/demo/ from a saved benchmark run.

    python scripts/build_demo.py --benchmark benchmark_long_fixed.json

Each demo is a real answer the model gave in that run, for a deed in
samples/dataset_long/. The automatic checks are run again with the current
code (they are deterministic, no API call), so the demo shows what the app
flags today. Nothing is invented: if a deed is missing from the run, the
script stops.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from deed_extractor.extractor import pdf_page_texts  # noqa: E402
from deed_extractor.schema import ExtractionResult  # noqa: E402
from deed_extractor.validators import validate_deed  # noqa: E402

DATASET = ROOT / "samples" / "dataset_long"
OUT = ROOT / "samples" / "demo"

DEMOS = [
    {
        "id": "kaek-misread",
        "pdf": "deed_01.pdf",
        "title": "A misread ΚΑΕΚ",
        "description": "Gemini swapped two digits of the land-registry code. It still has 12 digits and looks "
                       "valid; only the check against the PDF's own text catches it.",
    },
    {
        "id": "lawyers-present",
        "pdf": "deed_02.pdf",
        "title": "Lawyers at the signing",
        "description": "Two lawyers attend and everyone signs in person. Before a prompt fix, the model listed "
                       "the lawyers as representatives; here it correctly lists none.",
    },
    {
        "id": "missing-digit",
        "pdf": "deed_07.pdf",
        "title": "Parental provision, a digit dropped",
        "description": "A transfer from parent to child, with no price. The ΚΑΕΚ lost a digit: both the "
                       "format check and the text check flag it.",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--benchmark", type=Path, default=ROOT / "benchmark_long_fixed.json")
    parser.add_argument("--model", default="gemini-3.8-flash")
    args = parser.parse_args()

    run = json.loads(args.benchmark.read_text(encoding="utf-8"))
    answers = {doc["pdf"]: (doc.get("raw_results") or {}).get(args.model) for doc in run["documents"]}
    OUT.mkdir(exist_ok=True)

    for item in DEMOS:
        pdf = DATASET / item["pdf"]
        raw = answers.get(item["pdf"])
        if raw is None:
            raise SystemExit(f"{args.benchmark.name} has no {args.model} answer for {item['pdf']}")
        result = ExtractionResult.load(raw, model=args.model)

        texts = pdf_page_texts(str(pdf))
        full_text = " ".join(texts) if all(texts) else None
        result.validation = validate_deed(result.deed, text=full_text)
        result.meta.text_layer = full_text is not None
        result.meta.history_id = None
        result.meta.note = (
            f"A saved answer from a benchmark run ({result.meta.model}, page images only); the checks were run "
            "again with the current code. The tax IDs in these fictional deeds are deliberately invalid, so the "
            "check-digit test flags every one of them."
        )

        shutil.copyfile(pdf, OUT / f"{item['id']}.pdf")
        shutil.copyfile(pdf.with_suffix(".json"), OUT / f"{item['id']}.truth.json")
        (OUT / f"{item['id']}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        flagged = sorted({i.field for i in result.validation})
        print(f"{item['id']}: {len(result.validation)} flags on {', '.join(flagged)}")

    manifest = [{k: d[k] for k in ("id", "title", "description")} for d in DEMOS]
    (OUT / "demo.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(DEMOS)} demo deeds to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
