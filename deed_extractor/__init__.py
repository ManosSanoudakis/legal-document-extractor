"""Structured data from Greek notarial deeds with a vision language model.

- schema.py      the output schema sent to the model, and the result types
- extractor.py   PDF → page images + text → model → ExtractionResult; second look
- validators.py  checks on the extracted values (tax IDs, ΚΑΕΚ, dates, the PDF's text)
- accuracy.py    field-level scoring against known correct values
- evaluate.py    every model on one document, compared; benchmark.py over a dataset
- jobs.py        background jobs; history.py saved results; export.py Excel / CSV
- demo.py        saved answers for the demo deeds, shown without an API key
- api.py         the FastAPI app
"""
