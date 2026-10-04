FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Code lives in /app; the SQLite file (metadata.db) is created relative to the
# working directory, so we run from /data and mount a volume there.
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Non-root user + writable data dir for metadata.db
RUN useradd --create-home --uid 1000 appuser \
    && mkdir /data \
    && chown appuser:appuser /data
USER appuser
WORKDIR /data
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# Keep a single worker: the app runs an in-process cleanup scheduler and uses SQLite.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]