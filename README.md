# Legal Document Extractor

[![CI](https://github.com/ManosSanoudakis/legal-document-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/ManosSanoudakis/legal-document-extractor/actions/workflows/ci.yml)

Turns Greek notarial deeds (PDF, digital or scanned) into structured, checked data with Google Gemini vision: parties, property, transaction and notary, each value with the page and text it came from. A **FastAPI** backend and a **React + TypeScript** frontend, run together with Docker Compose.

![Extraction results for a demo deed](docs/screenshots/extraction.png)

| Source quotes | Editing | Batch |
|---|---|---|
| ![Sources tab with page links and quotes](docs/screenshots/sources.png) | ![Edit mode with input fields](docs/screenshots/editing.png) | ![Batch tab with a progress table](docs/screenshots/batch.png) |

## Try it

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). It opens on a **demo deed** with a real saved Gemini answer, so no API key is needed to look around. To extract your own PDFs, get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and paste it into **Settings**.

## Results

Field-level accuracy of `gemini-3.8-flash` on **synthetic** deeds: fictional, generated with known correct values. Every field is compared, including those that should be empty, so an invented value counts as wrong. 10 deeds per set:

| Set | Accuracy | Perfect deeds |
|---|---|---|
| Long deeds full of look-alike values | **100%** | 10/10 |
| Varied wording and layout | **100%** | 10/10 |
| Held-out: new deeds, a field worded and issued differently | **100%** | 10/10 |
| Harsh scans (stamps, signatures, no text layer) | **99.3%** | 9/10 |

Each step there was measured, fixed and measured again:

- **Lawyers listed as representatives**: 92.3% → 98.6%, after one sentence in the schema and prompt.
- **Misread land-registry codes** (ΚΑΕΚ) that still looked valid: sending the PDF's own text with each page and checking every value against it took them from 2 to 0, and made extraction faster (~39 s → ~27 s).
- **Building permits without their issuing office**: fixed in the field description and confirmed on a **held-out set**, so the fix is not fitted to the deeds it was found on.

These are synthetic deeds from one generator, ten per set and one run each, so expect lower accuracy on real documents. Details, the Flash-Lite comparison and the remaining errors are in [docs/evaluation.md](docs/evaluation.md); raw outputs in [docs/results/](docs/results/).

## What it does

- **Schema-enforced output**: Gemini's structured output fills a fixed Pydantic schema, so every answer has the same shape.
- **Source for every value**: the page and exact quote each value was read from; one click opens that page.
- **Automatic checks**: ΑΦΜ check digits, ΚΑΕΚ format, impossible dates and amounts, and, for a digital PDF, every copied value looked up in the PDF's text.
- **Review list and second look**: flagged values become a to-do list. "Second look" reads them again at higher resolution in one extra call, without showing the model its first answer.
- **Edit and export**: correct any value (the checks re-run), then download Excel or CSV.
- **Batch, background jobs and history**: up to 20 deeds with live progress and one combined export; results, corrections and ticks are saved, never the PDFs.
- **Model comparison**: Flash and Flash-Lite side by side on accuracy, completeness and speed.

## How it works

```
PDF ─┬─ page images (PyMuPDF) ─┐
     └─ text layer, if any ────┴─▶ Gemini (structured output) ─▶ checks ─▶ review, edit, export
                                                                     └──▶ history (SQLite)

Browser ──▶ nginx (:8080) ──/api──▶ FastAPI (:8000) ──▶ Gemini API
```

The backend is the [`deed_extractor/`](deed_extractor/) package; long work (extraction, evaluation, second look) runs as background jobs.

## Privacy and security

Built to run on one machine or an office network. Each user brings their own Gemini key, which is never stored or logged; PDFs are deleted after processing and only extracted values are kept. History is shared on the server by default; with `HISTORY=browser`, each visitor keeps their own in their browser and the server stores nothing. There are no logins yet, so do not expose it publicly, and use a paid key for real client deeds. See [Security](docs/design.md#security) for the full list.

All sample deeds are **fictional**. The app was developed against a real deed that cannot be shared (GDPR); the samples copy its format with invented names and numbers, and tax IDs that deliberately fail the check-digit test.

## Documentation

| | |
|---|---|
| [Evaluation](docs/evaluation.md) | How accuracy is measured, the datasets, full results and limits |
| [Design decisions](docs/design.md) | Why a VLM, the text check, second look vs an agent, jobs, history, security |
| [Development](docs/development.md) | Local setup, command line, tests, models, project structure |
| [API](docs/api.md) | Endpoints, extracted fields and assumptions |
