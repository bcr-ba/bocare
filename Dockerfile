# BoCare backend image. The desktop client is not included: it runs on the user's machine.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached and only rebuilt when the requirements change.
COPY requirements/backend.txt requirements/backend.txt
RUN pip install -r requirements/backend.txt

# Then the code and the processed corpus. The vector index is mounted at runtime
# (see docker-compose.yml): it is large, binary and depends on the embedding model.
COPY backend/app backend/app
COPY backend/data/processed backend/data/processed

# Run as an unprivileged user; it only needs to write the sessions database.
RUN useradd --create-home --uid 1000 bocare \
    && mkdir -p backend/data/state backend/data/index \
    && chown -R bocare backend/data
USER bocare

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
