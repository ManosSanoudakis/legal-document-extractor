# Legal Document Extractor

A full-stack application that extracts structured data from Greek notarial deeds using Google Gemini vision models — a **FastAPI** backend and a **React + TypeScript** frontend, run together with Docker Compose.

---

## Overview

The pipeline converts a PDF into page images, sends them to a Vision Language Model (VLM), and returns a structured JSON object with all key information from the deed — parties, property details, transaction data, and notary information.

An evaluation module benchmarks **Gemini 2.5 Flash** against **Gemini 2.5 Pro** on the same document, measuring extraction completeness and latency.

---

## Architecture

```
PDF
 └── pdf_to_images()        # PyMuPDF → JPEG pages (temporary, deleted after use)
      └── BaseExtractor
           └── GeminiExtractor.extract()   # PIL images + prompt → JSON
                └── run_pipeline()         # public entry point
                     ├── evaluate.py       # Flash vs Pro benchmark
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
Google AI Studio provides free-tier access to both Flash and Pro models, making it practical for this assignment. The architecture supports adding other providers (e.g. GPT-4o) by extending `BaseExtractor`.

### Why `BaseExtractor` as an ABC?
Enforces a consistent interface across providers. Any new backend must implement `extract()` — the rest of the pipeline doesn't need to change.

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
Without a ground-truth annotated dataset, exact accuracy cannot be measured. Instead, we use **completeness** (percentage of non-null fields) as a proxy, and **field-level disagreement** between models as a consistency signal. Latency is measured with `time.perf_counter()` for precision.

---

## Project Structure

```
.
├── api.py                          # FastAPI REST API
├── extractor.py                    # PDF → images → VLM → JSON
├── evaluate.py                     # Flash vs Pro benchmark
├── samples/
│   ├── sample_deed.pdf             # Fictional demo deed
│   └── make_sample_deed.py         # Script that generates it
├── frontend/                       # React + TypeScript + Tailwind (Vite)
│   ├── src/
│   │   ├── App.tsx                 # Layout, state, run logic
│   │   ├── api.ts                  # Typed API client
│   │   └── components/             # Settings, document picker, results, evaluation
│   ├── Dockerfile                  # Build with Node, serve with nginx
│   └── nginx.conf                  # Serves the app, proxies /api to the backend
├── Dockerfile                      # Backend image
├── docker-compose.yml              # api + web services
└── requirements.txt
```

> **Note:** The app was developed and tested against a real Greek notarial deed, which cannot be shared publicly due to GDPR — it contains personal data (names, ID numbers, addresses). Instead, `samples/sample_deed.pdf` is a **fictional** sale deed in the same format: every name, number and address is invented, and the tax IDs deliberately fail the official check-digit test so they cannot belong to a real person. Regenerate it with `python samples/make_sample_deed.py`.

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
python evaluate.py  --pdf samples/sample_deed.pdf
```

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Available models, limits, whether the sample exists |
| `GET` | `/api/sample` | The fictional sample deed (PDF) |
| `POST` | `/api/extract` | Multipart: `file` or `use_sample=true`, optional `model`. Header `X-Gemini-Key`. |
| `POST` | `/api/evaluate` | Multipart: `file` or `use_sample=true`. Header `X-Gemini-Key`. |

Uploads are limited to 20 MB and 30 pages, and model output is capped at 16k tokens.

---

## Usage

1. Get a free Gemini API key at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Paste it into **Settings** and pick a model (Flash: faster / Pro: more accurate)
3. Keep the **Sample deed** selected, or switch to **Upload PDF** and drop in your own deed
4. Click **Extract**

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
| Transaction | deed type, price, date |

---

## Assumptions

- A deed may have multiple sellers, buyers, and legal representatives — all are extracted as lists.
- In parental provision deeds, the parent is treated as the seller and the child as the buyer.
- If a field is not found in the document, it is returned as `null`.
- Uploaded PDFs and page images are written to temporary files and deleted after each request, so no document data is kept on disk.

---

## Potential Improvements

- **Ground-truth evaluation**: human-annotated dataset for exact accuracy measurement
- **Multi-document support**: different schemas and prompts per document type (lease, will, etc.)
- **Async processing**: parallel page processing for large documents
- **Authentication & usage limits**: needed before hosting the app publicly (see `TODO: SECURITY` in `api.py`)
- **Confidence scores**: prompt the model to return a confidence value per field
