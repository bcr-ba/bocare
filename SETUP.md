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

## 5. Test and lint

```bash
pytest                              # all 153 tests; no network, GPU or model needed
pytest backend/tests/safety -v      # only the behavioural safety checks
ruff check backend desktop
```

Tests replace the model and MedlinePlus with fakes, so they run anywhere in about a second. The desktop tests run Qt offscreen.

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
| Desktop shows "Server offline" | The backend isn't running, or `BOCARE_API_URL` points elsewhere. |
