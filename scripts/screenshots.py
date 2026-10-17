"""
Take the README screenshots by driving the running app in a browser.

    pip install playwright==1.52.0
    docker compose up -d
    python scripts/screenshots.py

The extraction screenshots show the first demo deed: a real answer Gemini
gave in a benchmark run, saved in samples/demo/, so no API key is needed.
The batch screenshot uploads the three demo deeds. Without GEMINI_API_KEY,
each is answered with its own saved result; with it, they are extracted for
real (3 requests) and a model evaluation of the first demo deed is added.
Either way no model results are invented.

Uses the installed Google Chrome (or Edge with --browser msedge), so no
browser download is needed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
DEMO_DIR = ROOT / "samples" / "demo"
DEMOS = json.loads((DEMO_DIR / "demo.json").read_text(encoding="utf-8"))
DEMO = DEMOS[0]


def saved_result(name: str) -> str:
    """The saved answer for an uploaded demo deed, by its file name (<id>.pdf)."""
    return (DEMO_DIR / name.removesuffix(".pdf")).with_suffix(".json").read_text(encoding="utf-8")


def demo_job(body: bytes) -> dict:
    """A finished job with one document per uploaded demo deed, each with its own saved result."""
    documents = []
    for i, name in enumerate(n.decode() for n in re.findall(rb'filename="([^"]+)"', body)):
        result = json.loads(saved_result(name))
        txn, issues = result["deed"]["transaction"], result["validation"]
        documents.append({
            "id": f"d{i}", "filename": name, "status": "done", "error": None,
            "elapsed_seconds": result["meta"]["elapsed_seconds"],
            "summary": {"deed_type": txn["deed_type"], "price": txn["price"], "date": txn["date"],
                        "flags": len(issues), "errors": sum(1 for i in issues if i["severity"] == "error")},
        })
    return {"id": "demo", "kind": "extract", "model": "gemini-3.8-flash", "status": "done", "documents": documents}


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
            files = [f"{d['id']}.pdf" for d in DEMOS]
            page.route("**/api/jobs", lambda route: route.fulfill(
                content_type="application/json", body=json.dumps(demo_job(route.request.post_data_buffer))))
            page.route("**/api/jobs/demo/documents/*", lambda route: route.fulfill(
                content_type="application/json", body=saved_result(files[int(route.request.url.rsplit("d", 1)[-1])])))

        # The first demo deed opens on its saved answer, with no key
        page.goto(args.url)
        page.get_by_role("radio", name=DEMO["title"]).wait_for(timeout=30_000)
        page.get_by_role("tab", name="Sources").wait_for(timeout=30_000)
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

        page.get_by_role("button", name="Done editing").click()
        page.get_by_label("Gemini API key").fill(key or "demo-key")
        page.get_by_role("tab", name="Batch").click()
        page.locator("input[type=file][multiple]").set_input_files([DEMO_DIR / f"{d['id']}.pdf" for d in DEMOS])
        page.get_by_role("button", name=f"Extract {len(DEMOS)} deeds").click()
        page.get_by_role("button", name="Excel (all)").wait_for(timeout=600_000)
        results_card(page).screenshot(path=OUT / "batch.png")
        print("Wrote docs/screenshots/batch.png")

        if key:
            page.get_by_role("tab", name="Model evaluation").click()
            page.get_by_role("button", name="Run evaluation").click()
            page.get_by_text("Wrong or missing values").wait_for(timeout=300_000)
            results_card(page).screenshot(path=OUT / "evaluation.png")
            print("Wrote docs/screenshots/evaluation.png")
        else:
            print("Skipped evaluation.png: set GEMINI_API_KEY to capture a real model comparison of the demo deed")

        browser.close()


if __name__ == "__main__":
    main()
