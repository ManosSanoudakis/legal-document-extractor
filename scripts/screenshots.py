"""
Take the README screenshots by driving the running app in a browser.

    pip install playwright==1.52.0
    docker compose up -d
    python scripts/screenshots.py

With GEMINI_API_KEY set, the screenshots show a real extraction and model
evaluation of the sample deed. Without it, /api/extract is answered with demo
data built from the sample's known answers (labelled "demo" in the UI), and
the evaluation screenshot is skipped, so no model results are invented.

Uses the installed Google Chrome (or Edge with --browser msedge), so no
browser download is needed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import fitz
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from validators import digits, norm_text, validate_deed  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
SAMPLE = ROOT / "samples" / "sample_deed.pdf"


def demo_result() -> dict:
    """The sample's correct answers, with sources taken from the PDF's own text."""
    truth = json.loads(SAMPLE.with_suffix(".json").read_text(encoding="utf-8"))
    with fitz.open(SAMPLE) as doc:
        lines = [(n, line) for n, page in enumerate(doc, start=1) for line in page.get_text().splitlines()]

    def find(value: object, numeric: bool) -> tuple[int, str] | None:
        for n, line in lines:
            hit = digits(value) in digits(line) if numeric else norm_text(value)[:20] in norm_text(line)
            if hit and (digits(value) if numeric else norm_text(value)):
                return n, line.strip()
        return None

    sources = []
    for section in ("notary", "property"):
        for key, value in truth[section].items():
            if isinstance(value, str) and (hit := find(value, key in {"kaek", "registry_number"})):
                sources.append({"field": f"{section}.{key}", "page": hit[0], "quote": hit[1]})
    for role in ("sellers", "buyers", "legal_representatives"):
        for i, person in enumerate(truth[role]):
            for key in ("full_name", "tax_id"):
                if person.get(key) and (hit := find(person[key], key == "tax_id")):
                    sources.append({"field": f"{role}[{i}].{key}", "page": hit[0], "quote": hit[1]})

    result = {**truth, "sources": sources}
    result["_validation"] = validate_deed(result)
    result["_meta"] = {"model": "demo (no API call)", "provider": "demo", "pages": len(fitz.open(SAMPLE)),
                       "elapsed_seconds": 0}
    return result


def results_card(page: Page):
    return page.locator("section").filter(has=page.get_by_role("tab", name="Extraction")).first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "msedge"])
    args = parser.parse_args()

    key = os.environ.get("GEMINI_API_KEY")
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=args.browser)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        if not key:
            demo = json.dumps(demo_result(), ensure_ascii=False)
            page.route("**/api/extract", lambda route: route.fulfill(content_type="application/json", body=demo))

        page.goto(args.url)
        page.get_by_label("Gemini API key").fill(key or "demo-key")
        page.get_by_role("button", name="Extract with").click()
        page.get_by_role("tab", name="Sources").wait_for(timeout=180_000)
        page.wait_for_timeout(1500)  # let the PDF preview render

        page.screenshot(path=OUT / "extraction.png", full_page=True)
        print("Wrote docs/screenshots/extraction.png")

        page.get_by_role("tab", name="Sources").click()
        results_card(page).screenshot(path=OUT / "sources.png")
        print("Wrote docs/screenshots/sources.png")

        page.get_by_role("tab", name="Property").click()
        page.get_by_role("button", name="Edit values").click()
        results_card(page).screenshot(path=OUT / "editing.png")
        print("Wrote docs/screenshots/editing.png")

        if key:
            page.get_by_role("tab", name="Model evaluation").click()
            page.get_by_role("button", name="Run evaluation").click()
            page.get_by_text("Wrong or missing values").wait_for(timeout=300_000)
            results_card(page).screenshot(path=OUT / "evaluation.png")
            print("Wrote docs/screenshots/evaluation.png")
        else:
            print("Skipped evaluation.png: set GEMINI_API_KEY to capture a real model comparison")

        browser.close()


if __name__ == "__main__":
    main()
