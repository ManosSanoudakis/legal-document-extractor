# Development

Running the app without Docker, the command line, tests, models and the code layout. [Back to the README](../README.md)

## Local setup (hot reload)

Requires Python 3.11+ and Node.js 20+.

```bash
# Terminal 1: backend on :8000
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn deed_extractor.api:app --reload

# Terminal 2: frontend on :5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Interactive API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

With Docker instead (`docker compose up --build`), the app is at [http://localhost:8080](http://localhost:8080) and history is kept in a Docker volume. Set `HISTORY_RETENTION_DAYS` to delete entries older than that many days.

## Command line

```bash
set GEMINI_API_KEY=your-key       # macOS/Linux: export GEMINI_API_KEY=your-key
python -m deed_extractor.extractor --pdf samples/sample_deed.pdf
python -m deed_extractor.evaluate  --pdf samples/sample_deed.pdf --truth samples/sample_deed.json
python -m deed_extractor.benchmark          # accuracy over samples/dataset, saved to benchmark_results.json
python -m deed_extractor.benchmark --dataset samples/dataset_long --output benchmark_long.json
```

`--dataset` takes any folder in `samples/` (see [Evaluation](evaluation.md#datasets)). The benchmark saves each model's raw output, so a change to the scoring can be re-applied later without new API calls. Add `--models gemini-3.8-flash` to spend only one model's quota: a free key allows about 20 Flash requests a day, one per deed.

## Tests and linting

```bash
pip install -r requirements-dev.txt
ruff check .
python -m pytest

cd frontend
npm run lint                     # oxlint, including the React hooks rules
npm test                         # Vitest
```

The tests mock Gemini, so they need no API key and make no network calls. GitHub Actions runs the same checks on every push, plus the frontend type-check and build (`npm ci` from the lockfile) and the Docker image builds. The frontend uses oxlint rather than ESLint because typescript-eslint does not support TypeScript 7 yet.

## Models

The defaults are `gemini-3.8-flash` and `gemini-3.5-flash-lite`, both available on a free API key. Free-tier quotas are small (Flash allows only a few dozen requests a day), and an evaluation uses one request per model. Gemini Pro has **no** free-tier quota and fails with `429 RESOURCE_EXHAUSTED … limit: 0` on a free key.

Google retires and renames models regularly. Override the list without code changes, e.g. to compare against Pro on a paid key:

```bash
set GEMINI_MODELS=gemini-3.8-flash,gemini-3.1-pro-preview   # first one is the default
docker compose up --build                                    # docker-compose.yml passes it to the api
```

## Sample data

Every deed in `samples/` is fictional. Regenerate the sample and all datasets with:

```bash
python samples/make_sample_deed.py --dataset 10 --scanned --long 10 --varied 10 --harsh --holdout 10
python scripts/build_demo.py      # the demo deeds, from a saved benchmark run
python scripts/screenshots.py     # the README screenshots (app running, Playwright installed)
```

## Project structure

```
.
├── deed_extractor/                 # The backend package
│   ├── api.py                      # FastAPI REST API
│   ├── extractor.py                # PDF → images (+ text) → VLM → ExtractionResult; second look
│   ├── schema.py                   # Pydantic schema sent to Gemini, and the result types
│   ├── validators.py               # ΑΦΜ, ΚΑΕΚ, date, amount and text-layer checks
│   ├── accuracy.py                 # Field-level scoring against ground truth
│   ├── evaluate.py                 # Flash vs Flash-Lite on one document
│   ├── benchmark.py                # Accuracy over a labelled dataset
│   ├── export.py                   # Excel / CSV export, one deed or many
│   ├── jobs.py                     # Background jobs with progress
│   ├── history.py                  # Saved results (SQLite), never PDFs
│   └── demo.py                     # Saved answers for the demo deeds
├── samples/
│   ├── sample_deed.pdf / .json     # Fictional sample deed + its correct values
│   ├── demo/                       # 3 long deeds with a saved Gemini answer and their correct values
│   ├── dataset*/                   # The labelled datasets (see docs/evaluation.md)
│   └── make_sample_deed.py         # Script that generates them
├── tests/                          # pytest suite (no API key needed)
├── scripts/
│   ├── build_demo.py               # Builds samples/demo/ from a saved benchmark run
│   └── screenshots.py              # Regenerates docs/screenshots/
├── docs/                           # These pages, screenshots and benchmark results
├── .github/workflows/ci.yml        # Lint, tests, frontend build, Docker build
├── frontend/                       # React + TypeScript + Tailwind (Vite)
│   ├── src/
│   │   ├── App.tsx                 # Layout, state, run logic
│   │   ├── api.ts                  # Typed API client
│   │   ├── *.test.ts               # Vitest tests for the deed and format helpers
│   │   └── components/             # Settings, document picker, results, review, batch, history, evaluation
│   ├── Dockerfile                  # Build with Node, serve with nginx
│   └── nginx.conf                  # Serves the app, proxies /api to the backend
├── Dockerfile                      # Backend image
├── docker-compose.yml              # api + web services
├── pyproject.toml                  # ruff and pytest settings
├── requirements.txt
└── requirements-dev.txt            # + pytest, ruff
```
