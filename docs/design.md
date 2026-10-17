# Design decisions

Why the app is built the way it is. [Back to the README](../README.md)

## Reading the document

### Why a VLM instead of a PDF text parser?
Greek notarial deeds are often scanned documents, and plain text extraction (`pdfplumber`, `pdfminer`) fails on scanned pages. A vision language model reads the document visually, the same way a human would.

### Why send the PDF's text as well, when there is one?
An image can be misread; a digital PDF's text cannot. The model gets both: the image for layout and the text for exact characters. In a run on the long deeds, the only two serious mistakes were misread ΚΑΕΚ digits (one pair swapped, one digit dropped). Looking every copied value up in the text catches both, with no false alarms on the true values of any labelled deed. Lines repeated on every page (headers, watermarks) are removed first, or they land in the middle of a value that runs onto the next page.

### Why DPI 150 for page images?
A trade-off between quality and speed. Lower DPI means smaller files and faster API calls but risks losing fine text. 150 DPI was sufficient for this document type; the second look uses 300 DPI on the few pages it needs.

### Why Gemini?
Google AI Studio's free tier covers Gemini Flash and Flash-Lite with vision and structured output, so anyone can run the app and its evaluation without billing. Pro has no free-tier quota; set `GEMINI_MODELS` to include it on a paid key. Other providers can be added by extending `BaseExtractor`, an abstract base class that fixes the interface (`extract()`, `recheck()`), so the rest of the pipeline does not change.

## Trusting the output

### Why structured output instead of "return only JSON" in the prompt?
Asking for JSON in the prompt works most of the time, but the model can still wrap it in markdown, rename a key or drop a field. With `response_schema`, Gemini is constrained to the Pydantic models in `schema.py`: every key is present, `deed_type` is one of four values, and numbers are numbers. Field descriptions in the schema double as per-field instructions. A plain JSON parser stays as a fallback.

### Why validate the output?
A vision model can misread one digit of a tax ID and still sound confident. Some errors can be caught without the source document: the Greek ΑΦΜ has a check digit, a ΚΑΕΚ has 12 digits, a deed cannot be signed in the future, and a price must be positive. Problems are reported, never silently corrected, so a person can verify them against the PDF.

### Why ask for a source quote per value?
A reviewer should not have to search a 20-page deed to verify one tax ID. Each value comes with its page and the text it was read from. The quotes also enable a cheap hallucination check: if a copied value (name, ΑΦΜ, ΚΑΕΚ) does not appear in its own quote, it is flagged. The model writes the quotes itself, so they can repeat its mistakes; the text-layer check does not have that weakness.

### Why a "second look" instead of an agent?
An agent loop (think → call a tool → think) costs several model calls per document and is hard to measure. The errors that remain are few and already flagged, so one extra call is enough: only the flagged fields, only the pages they were cited on, at 300 dpi, and without the first answer in the prompt so the second reading cannot simply repeat it.

### Why `area_sqm` and `price` as numbers, not strings?
To support calculations (e.g. price per m²) without extra parsing.

### Why a typed result?
Every extraction returns an `ExtractionResult` (in `schema.py`): the `deed`, its `meta` (model, pages, whether the text was checked, seconds, history id) and its `validation` issues. A model comparison returns an `EvaluationReport`. Keeping the deed apart from what was said about it means the deed can be edited, validated and exported as it is, and the API docs show the exact shape. Results saved in history in the older shape (deed keys next to `_meta` and `_validation`) are converted on load.

## Running it

### Why FastAPI + React instead of Streamlit?
Separating the API from the UI means the extraction service can be used by any client (scripts, other services) and the frontend has full control over layout and interaction. FastAPI also generates interactive API docs.

### Why background jobs?
An extraction takes 20–80 seconds. Holding an HTTP request open that long risks proxy and browser timeouts and shows the user nothing. A job returns at once and the browser polls each document's stage. Every long task goes this way (extraction, model evaluation and second look are all `POST /api/jobs` with a `task`), so there is one way to run slow work, one place for limits and one place for errors. Documents in a batch run one at a time because free-tier limits are per minute and per day, and a rejected key or exhausted quota stops the rest of the job instead of failing once per document.

Jobs are kept in the API process's memory, on purpose: one server for one office needs no queue or broker. The cost is that a restart loses running jobs, and two API processes would not see each other's jobs. Scaling out would mean a persistent queue (e.g. Redis or the existing SQLite) and separate worker processes; `JobStore` is the only class that would change.

### Why store results but not PDFs?
A deed is full of personal data. History keeps what the user needs to come back to (the extracted values, their corrections and which flags they checked) and nothing more. `HISTORY_RETENTION_DAYS` deletes old entries.

### Why can history live in the browser?
Without logins, a server history is shared by everyone who can reach the app. That suits one person or one office, not a demo open to several people. With `HISTORY=browser`, each visitor's history is kept in their own browser (local storage), so nobody sees anyone else's results and the server holds no one's data, with no accounts needed. The cost: it is lost if they clear their browser data, and does not follow them to another device. Both modes share one interface in the frontend (`history.ts`), so the rest of the app does not know which is in use.

### Why does each user bring their own API key?
No key is stored on the server. The browser keeps the key in memory and sends it per request in the `X-Gemini-Key` header, so nobody can spend someone else's quota. For real client deeds, use a paid key: Google's terms allow content sent on the free tier to be used to improve its products, which personal data should not be. A firm would then keep its own key on the server and add logins.

### Why a demo that needs no key?
Most people looking at the app will not make an API key first. The demo deeds open at once on answers Gemini really gave in a benchmark run (`samples/demo/`, built by `scripts/build_demo.py`), with the automatic checks run again by the current code. Nothing is invented, and one of them is the ΚΑΕΚ misread that only the text check catches. With a key, the same deeds can be extracted or evaluated live, and the evaluation scores accuracy because their correct values are known.

## Security

The app is built to run on one machine or an office network, not as a public service.

**What it does:**
- **API keys**: each request carries the caller's key in the `X-Gemini-Key` header. The browser keeps it in memory only (never in storage), the server never stores or logs it, and a background job drops it when the job ends.
- **Documents**: an uploaded PDF and its page images exist only as temporary files while they are processed. History keeps the extracted values, corrections and review ticks, never the PDF, and `HISTORY_RETENTION_DAYS` deletes old entries.
- **Input limits**: PDFs only (checked by content, not file name), 20 MB and 30 pages each, 20 files per batch, 4 jobs at a time, 30 fields per second look, and model output capped at 16k tokens.
- **The model cannot act**: it only fills in a fixed schema. It has no tools, cannot call anything, and its answer is shown as text (React escapes it). A deed written to mislead it can at most produce wrong values, and those face the same checks as any others.
- **Exports**: a value that starts like a spreadsheet formula (`=`, `+`, `-`, `@`) is written as text, so a malicious document cannot plant a formula in the Excel or CSV file (CSV injection).
- **Demo files**: served only by id from a fixed list, never by a path from the request.

**What it does not do (needed before hosting it for others):**
- **Logins.** In server history mode, anyone who can reach the server sees and edits the same history (`HISTORY=browser` gives each visitor their own instead).
- **Limits per user.** The job limit is global; one person can fill it.
- **A server-side key** for a firm's own account, ideally a paid one (see above).
- **HTTPS.** Run it behind a proxy that provides it.

## Possible improvements

- **Real-document evaluation**: the labelled datasets are synthetic; a set of anonymised real deeds would give a more honest accuracy figure
- **Highlight in the preview**: draw a box around the quoted text on the page instead of only jumping to the page
- **Add or remove parties while editing**: editing currently changes existing values only
- **Native PDF input**: Gemini accepts PDFs directly, which would remove the image conversion step (worth measuring first: it gives up control over resolution and the removal of repeated page lines)
- **Multi-document support**: different schemas and prompts per document type (lease, will, etc.)
- **Logins and usage limits**: needed before hosting the app publicly
- **Confidence scores**: prompt the model to return a confidence value per field
- **Persistent jobs**: a queue and separate workers, so jobs survive a restart and the API can run as several processes
- **Mixed PDFs**: the text check runs only when every page has text; a deed with some scanned pages could check the pages that do
