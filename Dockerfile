FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py extractor.py evaluate.py schema.py validators.py accuracy.py export.py jobs.py ./
COPY samples/sample_deed.pdf samples/sample_deed.json samples/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
