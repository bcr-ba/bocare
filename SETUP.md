# Setup

Installation, configuration and testing. See [README.md](README.md) for what BoCare is and how it works.

## Requirements

- Python 3.10 or newer
- [Ollama](https://ollama.com), running locally, for the default local model
- About 8 GB of GPU memory for `qwen3:8b` (it also runs on CPU, much more slowly)

## 1. Install

```bash
python -m venv .venv
.venv\Scripts\activate              # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Pull the models

```bash
ollama pull qwen3:8b                # main model (5.2 GB)
ollama pull qwen3:4b                # fallback when the main model fails (2.5 GB)
ollama pull qwen3-embedding:0.6b    # embedding model for semantic search (0.6 GB)
```

## 2b. Build the search index

```bash
python scripts/build_corpus.py --download   # MedlinePlus export -> backend/data/processed/chunks.jsonl
python scripts/build_index.py               # embeddings -> backend/data/index/ (about 5 minutes)
python evaluation/retrieval/run_retrieval_eval.py dense_qwen3   # optional: measure retrieval quality
```

Without an index the server still runs, using MedlinePlus keyword search, and logs a warning.

## 3. Configure (optional)

Defaults live in [backend/app/config/settings.yml](backend/app/config/settings.yml) and work as they are. To change a value on your machine only, copy `.env.example` to `.env` and set the key in upper case:

```bash
cp .env.example .env
```

```ini
OLLAMA_MODEL=qwen3:14b          # any key from settings.yml
LLM_PROVIDER=openrouter         # use a hosted model instead of Ollama
OPENROUTER_API_KEY=sk-or-...    # secrets go in .env only, never in settings.yml
```

`.env` is gitignored. What every configuration file controls is described in [backend/app/config/README.md](backend/app/config/README.md).

## 4. Run

Backend, from the repository root:

```bash
uvicorn app.main:app --app-dir backend --reload
```

The API is at http://127.0.0.1:8000 and its interactive documentation at http://127.0.0.1:8000/docs. The model is loaded in the background at startup; `GET /health` shows whether it is available.

Desktop client, in a second terminal:

```bash
python -m desktop.main
```

To point it at another server, set `BOCARE_API_URL` (for example `http://192.168.1.20:8000`).

## 4b. Run with Docker (backend + trace viewer)

Ollama stays on your machine (it uses the GPU directly); the models must be pulled and the index built
on the host first (steps 2 and 2b).

```bash
docker compose up --build -d     # backend on http://localhost:8000, Jaeger on http://localhost:16686
docker compose logs -f backend   # follow the logs
docker compose down              # stop (sessions are kept in the bocare-state volume)
```

The desktop client works unchanged against the containerised backend.

## Traces

Every message produces a trace: one span per stage with its duration, the urgency level, the number of
sources, token counts and verification results. Spans never contain the patient's text.

- In Docker, traces go to Jaeger automatically: open http://localhost:16686, pick the service
  `bocare-backend`, then **Find Traces**.
- Running the backend directly on your machine: set `TRACING_EXPORTER=otlp` (Jaeger must run:
  `docker compose up -d jaeger`) or `TRACING_EXPORTER=console` to print spans in the terminal.

## Sessions

Sessions are stored in `backend/data/state/bocare.db` (SQLite; in Docker, the `bocare-state` volume) and
deleted after `session_retention_days` (7) without activity. They contain the patient's messages: the file
is gitignored and must never be shared. `STATE_BACKEND=memory` keeps nothing on disk.

## 5. Test and lint

```bash
pytest                              # all 185 tests; no network, GPU or model needed
pytest backend/tests/safety -v      # only the behavioural safety checks
ruff check backend desktop
```

Tests replace the models with fakes, so they run anywhere in about a second; the desktop tests run Qt offscreen.
GitHub Actions runs the same checks on every push, plus a Docker build with a smoke test and a secret scan
(`.github/workflows/ci.yml`).

## Common problems

| Symptom | Cause and fix |
|---|---|
| Server stops at startup with `Invalid config/...yml` | A YAML file has a typo, a missing translation or an invalid regex. The message names the file and field. |
| `"llm_configured": false` on `/health` | Ollama isn't running, or neither `qwen3:8b` nor `qwen3:4b` is pulled. Run `ollama list`. |
| First answer is slow or times out | The model is still loading into GPU memory (up to a minute after startup). Later answers take 15-30 s. |
| Answers come back as "service unavailable" | Both models failed. Check that Ollama is running and that nothing else is using the GPU (`ollama ps`). |
| No sources shown | The index isn't built (the log says "Falling back") or the embedding model isn't pulled. |
| Every Ollama call takes 2 s more than it should | `OLLAMA_URL` uses `localhost`: on Windows it tries IPv6 first. Use `127.0.0.1`. |
| Port 8000 already in use | An old server is still running; stop it before starting a new one, or you'll be testing old code. |
| `docker compose up` fails: port 8000 already allocated | A backend started outside Docker is still running; stop it first. Check *what* holds the port before stopping it: it can be Docker itself. |
| No traces in Jaeger | `TRACING_EXPORTER` isn't `otlp`, or Jaeger isn't running (`docker compose ps`). |
| Desktop shows "Server offline" | The backend isn't running, or `BOCARE_API_URL` points elsewhere. |
