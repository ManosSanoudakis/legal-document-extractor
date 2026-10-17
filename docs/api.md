# API

The REST API behind the app. With the backend running, interactive docs are at [localhost:8000/docs](http://localhost:8000/docs). [Back to the README](../README.md)

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Available models, limits, whether the sample exists, the demo deeds |
| `GET` | `/api/sample` | The fictional sample deed (PDF) |
| `GET` | `/api/demo/{id}` | A demo deed's saved result. No key needed. |
| `GET` | `/api/demo/{id}/pdf` | A demo deed (PDF) |
| `POST` | `/api/jobs` | Start long-running work; returns a job at once (see below) |
| `GET` | `/api/jobs/{id}` | Progress: each document's stage, time and a short summary. Finished jobs are kept for an hour. |
| `GET` | `/api/jobs/{id}/documents/{doc}` | One document's result: an `ExtractionResult`, an `EvaluationReport` or a re-check, by task |
| `GET` | `/api/history` | Saved results, newest first, with what is left to check. Server history mode only (`404` with `HISTORY=browser`) |
| `GET` / `PUT` / `DELETE` | `/api/history/{id}` | One saved result: read it, save corrections and review ticks, or delete it. Server history mode only |
| `POST` | `/api/validate` | JSON deed (e.g. after manual corrections). Returns `{"issues": [...]}` |
| `POST` | `/api/export?format=xlsx\|csv` | JSON deed. Returns an Excel file (sheets *Deed* and *People*) or a CSV |
| `POST` | `/api/export/batch?format=xlsx\|csv` | `{"deeds": [{"name": ..., "deed": ...}]}`. One row per deed (sheets *Deeds* and *People*) |

### Jobs

`POST /api/jobs` is multipart, with the caller's key in the `X-Gemini-Key` header. The document is one of `files`, `use_sample=true` or `demo={id}`. The `task` says what to do:

| `task` | Documents | Other fields | Result |
|---|---|---|---|
| `extract` (default) | Up to 20 | optional `model` | `ExtractionResult`, also saved to history in server mode |
| `evaluate` | One | | `EvaluationReport`: every model compared, and scored for the sample and demo deeds |
| `recheck` | One | `deed` and `fields` (JSON), optional `model` | A second reading of those fields |

Uploads are limited to 20 MB and 30 pages, and model output is capped at 16k tokens. Busy (429) and server (5xx) errors from Gemini are retried up to 3 times with backoff; a rejected key or exhausted quota stops the rest of the job.

### Results

Every `ExtractionResult` has:
- `deed`: the extracted values, with `sources` (page and quote per value)
- `validation`: failed checks, empty when all pass
- `meta`: model, pages, whether the text was checked, seconds, and the history id
- `error`: set if the model's answer could not be parsed

## Extracted fields

| Section | Fields |
|---|---|
| Notary | name, location, registry number |
| Sellers | full name, tax ID, ID document, address |
| Buyers | full name, tax ID, ID document, address |
| Legal representatives | full name, represents, tax ID, ID document |
| Property | type, address, municipal unit, floor, area (m²), ΚΑΕΚ, building permit |
| Transaction | deed type (`sale`, `parental_provision`, `donation`, `other`), price, date (YYYY-MM-DD) |

## Assumptions

- A deed may have several sellers, buyers and legal representatives; all are extracted as lists.
- In a parental provision or donation, the parent or donor is treated as the seller and the child or recipient as the buyer.
- A field not found in the document is returned as `null`.
- Uploaded PDFs and page images are written to temporary files and deleted after processing; only the extracted results go to history.
