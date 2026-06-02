# Legal Document Extractor

A Streamlit application that extracts structured data from Greek notarial deeds using Google Gemini Vision models.

---

## Overview

The pipeline converts a PDF into page images, sends them to a Vision Language Model (VLM), and returns a structured JSON object with all key information from the deed — parties, property details, transaction data, and notary information.

An evaluation module benchmarks **Gemini 2.5 Flash** against **Gemini 2.5 Pro** on the same document, measuring extraction completeness and latency.

---

## Architecture

```
PDF
 └── pdf_to_images()        # PyMuPDF → JPEG pages (cached on disk)
      └── BaseExtractor
           └── GeminiExtractor.extract()   # PIL images + prompt → JSON
                └── run_pipeline()         # public entry point
                     ├── app.py            # Streamlit UI
                     └── evaluate.py       # Flash vs Pro benchmark
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

### Evaluation methodology
Without a ground-truth annotated dataset, exact accuracy cannot be measured. Instead, we use **completeness** (percentage of non-null fields) as a proxy, and **field-level disagreement** between models as a consistency signal. Latency is measured with `time.perf_counter()` for precision.

---

## Project Structure

```
.
├── app.py                          # Streamlit UI (Extraction + Evaluation tabs)
├── extractor.py                    # PDF → images → VLM → JSON
├── evaluate.py                     # Flash vs Pro benchmark
├── Dockerfile                      
├── docker-compose.yml              
├── requirements.txt                
└── simbolaio-agorapolisias-public.pdf   # Sample notarial deed
```

---

## Setup & Run

### Option 1 — Docker (recommended)

```bash
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### Option 2 — Local Python

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Usage

1. Get a free Gemini API key at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Enter it in the sidebar
3. Select a model (Flash: faster / Pro: more accurate)
4. Upload a PDF or use the included sample document
5. Click **Run Extraction**

To benchmark both models, go to the **Evaluation** tab and click **Run Evaluation**.

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
- Page images are cached in `pages/` to avoid re-processing on subsequent runs.

---

## Potential Improvements

- **Ground-truth evaluation**: human-annotated dataset for exact accuracy measurement
- **Multi-document support**: different schemas and prompts per document type (lease, will, etc.)
- **Async processing**: parallel page processing for large documents
- **Confidence scores**: prompt the model to return a confidence value per field
