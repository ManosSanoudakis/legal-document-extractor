# Legal Document Extractor

[![CI](https://github.com/ManosSanoudakis/legal-document-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/ManosSanoudakis/legal-document-extractor/actions/workflows/ci.yml)

A full-stack application that extracts structured data from Greek notarial deeds using Google Gemini vision models — a **FastAPI** backend and a **React + TypeScript** frontend, run together with Docker Compose.

---

## Overview

The pipeline converts a PDF into page images, sends them to a Vision Language Model (VLM), and returns a structured JSON object with all key information from the deed — parties, property details, transaction data, and notary information.

- **Schema-enforced output**: Gemini's structured output mode constrains the response to a Pydantic schema, so every response has the same shape.
- **Automatic checks**: every extraction is validated (ΑΦΜ check digits, ΚΑΕΚ format, impossible dates, non-positive amounts) and problems are shown next to the results.
- **Measured accuracy**: a labelled set of fictional deeds gives field-level accuracy, not just a count of filled-in fields.
- **Model comparison**: Gemini Flash and Flash-Lite run side by side on the same document, scored on accuracy, completeness and latency. Both are on the free tier; Pro can be added on a paid key.
- **Source for every value**: the model cites the page and exact text each value came from; one click shows that page in the preview.
- **Review and export**: correct any value in place (checks re-run automatically), then download Excel or CSV.

![Extraction results for the fictional sample deed](docs/screenshots/extraction.png)

<sub>Screenshots use the fictional sample deed with demo data (no model call). Regenerate them from a real run with `python scripts/screenshots.py` and a `GEMINI_API_KEY`.</sub>

| Source quotes | Editing |
|---|---|
| ![Sources tab with page links and quotes](docs/screenshots/sources.png) | ![Edit mode with input fields](docs/screenshots/editing.png) |

---

## Architecture

```
PDF
 └── pdf_to_images()        # PyMuPDF → JPEG pages (temporary, deleted after use)
      └── BaseExtractor
           └── GeminiExtractor.extract()   # images + prompt → JSON constrained by schema.Deed
                ├── validate_deed()        # ΑΦΜ, ΚΑΕΚ, date and amount checks → _validation
                └── run_pipeline()         # public entry point
                     ├── evaluate.py       # Flash vs Flash-Lite on one document (+ accuracy if truth known)
                     ├── benchmark.py      # accuracy over the labelled dataset
                     └── api.py            # FastAPI REST endpoints
                          └── frontend/    # React UI (served by nginx, proxies /api)
```

```
Browser ──▶ nginx (web, :8080) ──/api──▶ FastAPI (api, :8000) ──▶ Gemini API
              └── React static build
```

---

## Design Decisions

### Why a VLM instead of a PDF text parser?
Greek notarial deeds are often scanned documents — plain text extraction via `pdfplumber` or `pdfminer` fails on scanned pages. A VLM reads the document visually, the same way a human would.

### Why Gemini?
Google AI Studio's free tier covers Gemini Flash and Flash-Lite with vision and structured output, so anyone can run the app and its evaluation without billing. (Pro has no free-tier quota; set `GEMINI_MODELS` to include it on a paid key.) The architecture supports adding other providers (e.g. GPT-4o) by extending `BaseExtractor`.

### Why `BaseExtractor` as an ABC?
Enforces a consistent interface across providers. Any new backend must implement `extract()` — the rest of the pipeline doesn't need to change.

### Why structured output instead of "return only JSON" in the prompt?
Asking for JSON in the prompt works most of the time, but the model can still wrap it in markdown, rename a key or drop a field. With `response_schema`, Gemini is constrained to the Pydantic models in `schema.py`: every key is present, `deed_type` is one of four values, and numbers are numbers. Field descriptions in the schema double as per-field instructions. The old JSON parser stays as a fallback.

### Why validate the output?
A vision model can misread one digit of a tax ID and still sound confident. Some errors can be caught without the source document: the Greek ΑΦΜ has a check digit, a ΚΑΕΚ has 12 digits, a deed cannot be signed in the future, and a price must be positive. Problems are reported, never silently corrected, so a person can verify them against the PDF.

### Why ask for a source quote per value?
A reviewer should not have to search a 20-page deed to verify one tax ID. Each value comes with its page and the text it was read from. The quotes also enable a cheap hallucination check: if a copied value (name, ΑΦΜ, ΚΑΕΚ) does not appear in its own quote, it is flagged.

### Why `area_sqm` and `price` as numbers, not strings?
To support downstream calculations (e.g. price per sqm) without extra parsing. A string would require conversion every time.

### Why `_meta` in every response?
Observability — knowing which model ran, how many pages were processed, and how long it took is essential for debugging and evaluation.

### Why DPI 150 for page images?
A trade-off between quality and speed. Lower DPI means smaller files and faster API calls but risks losing fine text. 150 DPI was sufficient for this document type.

### Why FastAPI + React instead of Streamlit?
Separating the API from the UI means the extraction service can be used by any client (scripts, other services) and the frontend has full control over layout and interaction. FastAPI also generates interactive API docs automatically.

### Why does each user bring their own API key?
No key is stored on the server. The browser keeps the key in memory and sends it per request in the `X-Gemini-Key` header, so nobody can spend someone else's quota.

### Evaluation methodology
Real deeds cannot be shared, so `samples/make_sample_deed.py` generates fictional deeds together with a JSON file of the correct values. That makes three measurements possible:

- **Accuracy**: every field in the ground truth is compared with the extraction, including fields that should be null, so an invented value counts as wrong. An invented party (for example a lawyer listed as a legal representative) is wrong in every one of its fields, like a missed one. Comparison ignores formatting only (accents, case, spacing, Latin look-alike letters in ID numbers, a name with or without the patronymic (names only: an address without its city is wrong), a municipal unit with or without the "Δημοτική Ενότητα" label). When both models score the same, the faster one is named the winner and the report marks it as a tie.
- **Completeness**: the share of fields that are filled in. Used when no ground truth exists (any uploaded PDF). It rewards invented values, so it is a weak proxy.
- **Disagreement**: fields where the two models return different values, a consistency signal that needs no ground truth.

Latency is measured with `time.perf_counter()`. Both models run in parallel, so an evaluation takes as long as the slower model.

The same ten deeds also exist as **simulated scans** in `samples/dataset_scanned/`: rendered to grayscale images with slight rotation, blur, grain, uneven contrast and heavy JPEG compression, with no text layer. Comparing both sets shows how much scan quality costs.

The short deeds state each value once, so strong and weak models score alike. **Long deeds** in `samples/dataset_long/` (6–8 pages, in larger, widely spaced type like real deeds) keep the same kind of correct answers but surround them with look-alike values: a title history of earlier owners, deed numbers, notaries, dates and prices; other units in the building with their own areas and ΚΑΕΚ; lawyers and an engineer with tax IDs; the assessed value next to the price; tax, mortgage and fee amounts; and a list of attached documents with their own numbers and dates. A model that picks up a look-alike value is marked wrong.

**Limitation**: real deeds also have stamps, signatures, handwriting and photocopy artefacts that the simulation does not reproduce, so accuracy on real documents will likely be lower still.

---

## Project Structure

```
.
├── api.py                          # FastAPI REST API
├── extractor.py                    # PDF → images → VLM → JSON
├── schema.py                       # Pydantic output schema sent to Gemini
├── validators.py                   # ΑΦΜ, ΚΑΕΚ, date and amount checks
├── accuracy.py                     # Field-level scoring against ground truth
├── evaluate.py                     # Flash vs Flash-Lite on one document
├── benchmark.py                    # Accuracy over the labelled dataset
├── export.py                       # Excel / CSV export
├── samples/
│   ├── sample_deed.pdf / .json     # Fictional demo deed + its correct values
│   ├── dataset/                    # 10 more fictional deeds, each with a .json
│   ├── dataset_scanned/            # The same 10 as simulated scans
│   ├── dataset_long/               # 10 long deeds full of look-alike values
│   └── make_sample_deed.py         # Script that generates them
├── tests/                          # pytest suite (no API key needed)
├── scripts/screenshots.py          # Regenerates docs/screenshots/
├── .github/workflows/ci.yml        # Lint, tests, frontend build, Docker build
├── frontend/                       # React + TypeScript + Tailwind (Vite)
│   ├── src/
│   │   ├── App.tsx                 # Layout, state, run logic
│   │   ├── api.ts                  # Typed API client
│   │   └── components/             # Settings, document picker, results, evaluation
│   ├── Dockerfile                  # Build with Node, serve with nginx
│   └── nginx.conf                  # Serves the app, proxies /api to the backend
├── Dockerfile                      # Backend image
├── docker-compose.yml              # api + web services
├── pyproject.toml                  # ruff and pytest settings
├── requirements.txt
└── requirements-dev.txt            # + pytest, ruff
```

> **Note:** The app was developed and tested against a real Greek notarial deed, which cannot be shared publicly due to GDPR — it contains personal data (names, ID numbers, addresses). Instead, `samples/sample_deed.pdf` is a **fictional** sale deed in the same format: every name, number and address is invented, and the tax IDs deliberately fail the official check-digit test so they cannot belong to a real person (which is also why the app's checks flag them). Regenerate the sample and all datasets with `python samples/make_sample_deed.py --dataset 10 --scanned --long 10`.

---

## Setup & Run

### Option 1 — Docker (recommended)

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080) in your browser.

### Option 2 — Local development (hot reload)

Requires Python 3.11+ and Node.js 20+.

```bash
# Terminal 1 — backend on :8000
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload

# Terminal 2 — frontend on :5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Interactive API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

### Option 3 — Command line

```bash
set GEMINI_API_KEY=your-key       # macOS/Linux: export GEMINI_API_KEY=your-key
python extractor.py --pdf samples/sample_deed.pdf
python evaluate.py  --pdf samples/sample_deed.pdf --truth samples/sample_deed.json
python benchmark.py                # accuracy over samples/dataset, saved to benchmark_results.json
python benchmark.py --dataset samples/dataset_scanned --output benchmark_scanned.json
python benchmark.py --dataset samples/dataset_long --output benchmark_long.json
```

### Tests and linting

```bash
pip install -r requirements-dev.txt
ruff check .
python -m pytest
```

The tests mock Gemini, so they need no API key and make no network calls. GitHub Actions runs the same checks on every push, plus the frontend type-check and build (`npm ci` from the lockfile) and the Docker image builds.

### Models

The defaults are `gemini-3.8-flash` and `gemini-3.5-flash-lite`, both available on a free API key. Free-tier quotas are small (Flash allows only a few dozen requests a day), and an evaluation uses one request per model. Gemini Pro has **no** free-tier quota and fails with `429 RESOURCE_EXHAUSTED … limit: 0` on a free key.

Google retires and renames models regularly. Override the list without code changes, e.g. to compare against Pro on a paid key:

```bash
set GEMINI_MODELS=gemini-3.8-flash,gemini-3.1-pro-preview   # first one is the default
docker compose up --build                                    # docker-compose.yml passes it to the api
```

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Available models, limits, whether the sample exists |
| `GET` | `/api/sample` | The fictional sample deed (PDF) |
| `POST` | `/api/extract` | Multipart: `file` or `use_sample=true`, optional `model`. Header `X-Gemini-Key`. |
| `POST` | `/api/evaluate` | Multipart: `file` or `use_sample=true`. Header `X-Gemini-Key`. For the sample, also scores accuracy against its known answers. |
| `POST` | `/api/validate` | JSON deed (e.g. after manual corrections). Returns `{"issues": [...]}`. |
| `POST` | `/api/export?format=xlsx\|csv` | JSON deed. Returns an Excel file (sheets *Deed* and *People*) or a CSV. |

Uploads are limited to 20 MB and 30 pages, and model output is capped at 16k tokens. Busy (429) and server (5xx) errors from Gemini are retried up to 3 times with backoff. Every extraction response includes `sources` (page and quote per value), `_validation` (failed checks, empty when all pass) and `_meta` (model, pages, seconds).

---

## Usage

1. Get a free Gemini API key at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Paste it into **Settings** and pick a model (Flash: stronger / Flash-Lite: faster, larger free quota)
3. Keep the **Sample deed** selected, or switch to **Upload PDF** and drop in your own deed
4. Click **Extract**
5. Check flagged values: hover a page link (**p. 1**) to see the quote, click it to open that page in the preview
6. Click **Edit values** to correct anything, then download **Excel** or **CSV**

To benchmark both models, open the **Model evaluation** tab and click **Run evaluation**.

---

## Extracted Fields

| Section | Fields |
|---|---|
| Notary | name, location, registry number |
| Sellers | full name, tax ID, ID document, address |
| Buyers | full name, tax ID, ID document, address |
| Legal Representatives | full name, represents, tax ID, ID document |
| Property | type, address, municipal unit, floor, area (sqm), KAEK, building permit |
| Transaction | deed type (`sale`, `parental_provision`, `donation`, `other`), price, date (YYYY-MM-DD) |

---

## Assumptions

- A deed may have multiple sellers, buyers, and legal representatives — all are extracted as lists.
- In parental provision deeds, the parent is treated as the seller and the child as the buyer.
- If a field is not found in the document, it is returned as `null`.
- Uploaded PDFs and page images are written to temporary files and deleted after each request, so no document data is kept on disk.

---

## Potential Improvements

- **Real-document evaluation**: the labelled datasets are synthetic; a set of anonymised real deeds would give a more honest accuracy figure
- **Highlight in the preview**: draw a box around the quoted text on the page instead of only jumping to the page
- **Add or remove parties while editing**: editing currently changes existing values only
- **Native PDF input**: Gemini accepts PDFs directly, which would remove the image conversion step
- **Multi-document support**: different schemas and prompts per document type (lease, will, etc.)
- **Async processing**: parallel page processing for large documents
- **Authentication & usage limits**: needed before hosting the app publicly (see `TODO: SECURITY` in `api.py`)
- **Confidence scores**: prompt the model to return a confidence value per field
