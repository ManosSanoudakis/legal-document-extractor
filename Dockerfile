FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY deed_extractor/ deed_extractor/
COPY samples/sample_deed.pdf samples/sample_deed.json samples/
COPY samples/demo/ samples/demo/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "deed_extractor.api:app", "--host", "0.0.0.0", "--port", "8000"]
