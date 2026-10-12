# Backend

FastAPI service that turns a patient's message into an urgency level, a recommendation and a verified explanation. Run it with `uvicorn app.main:app --app-dir backend` from the repository root (see [SETUP.md](../SETUP.md)).

## Layout

| Folder | Contents |
|---|---|
| `app/api/` | Routes: `POST /chat`, `POST /chat/stream` (server-sent events), `GET /health` |
| `app/core/` | `settings.py` (runtime settings), `config_loader.py` (loads and validates the YAML files), logging, request IDs, error handlers |
| `app/config/` | Behaviour as YAML: triage rules, care paths, safety, verification, texts. See [config/README.md](app/config/README.md) |
| `app/prompts/` | Prompts as YAML, separated from the code that sends them |
| `app/schemas/` | Pydantic contracts: API requests and responses (`api.py`), the model's answer and the judge's verdict (`llm.py`), every config file (`config.py`) |
| `app/pipeline/` | The steps a message goes through (below) |
| `app/llm/` | Ollama and OpenRouter clients; prompt builders |
| `app/state/` | `SessionStore` interface; in-memory and SQLite implementations with migrations and retention |
| `app/retrieval/` | Corpus parsing and chunking, embeddings (Ollama or fastembed), vector index, semantic retriever; the MedlinePlus keyword retriever is the fallback |
| `tests/` | `unit/`, `safety/` (behavioural safety checks), `integration/` (API and streaming with fakes) |

## How a message flows

`Orchestrator` (in `pipeline/orchestrator.py`) splits each message into a fast, deterministic part and a slow part:

**`prepare()`: fast, no model, under 0.5 s**
1. `preprocessor`: detect French or English; answer greetings, thanks and bare requests for help with a fixed reply.
2. `safety`: length limits, rate limit, prompt-injection filter; flag self-harm and medication requests.
3. `triage`: urgency 1-5 from the rules in `triage.yml`. It never goes down within a session.
4. `triage.care_recommendation` + `follow_up`: the advice for that level and the next questions to ask.

**`complete()`: slow, 15-30 s with a local model**

5. `responder`: retrieve the closest MedlinePlus passages by semantic search, then ask the model for a JSON answer (`summary`, `possible_explanations` with `source_ids`, `warning_signs`, `self_care`, `clarifying_question`).
6. `postprocessor`: remove self-references, reasoning tags, preambles and citation numbers that match no source.
7. `verifier`: reject delay advice at high urgency, doses and diagnostic certainty; from `judge_min_level`, a judge checks claims against their sources. A rejected answer is regenerated once with the reason; a second rejection returns only the fixed recommendation.

`POST /chat` runs both parts and returns one response. `POST /chat/stream` sends the result of `prepare()` immediately as a `triage` event, then `sources` and `status` events, and the verified answer last as `done`. Nothing generated is sent before it has been verified.

## Design rules

- **The model never decides the urgency.** It is told the level and must stay consistent with it.
- **Nothing generated reaches the patient unchecked.** Failure codes are logged and returned in `verification.failed_checks`; the generated text is never logged.
- **One trace per message.** `core/tracing.py` opens a `chat.turn` span with children for each stage; streaming keeps them in one trace although its steps run on different threads.
- **Health data stays out of the logs and traces.** Logs hold session IDs, levels, matched symptom names and failure codes, never the message.
- **No behaviour hard-coded in Python.** Rules, thresholds, texts and prompts are in `config/` and `prompts/`, validated at startup.

## Extending

- **Add a symptom or keyword:** edit `config/triage.yml` (urgency) and `config/medical_terms.yml` (sources). No code change.
- **Add a language:** add its texts to every YAML file that has `fr`/`en` entries and to `schemas/config.py`'s `LANGUAGES`; the loader then rejects any file missing a translation.
- **Replace retrieval:** implement `retrieval/base.Retriever.search()` and pass it to `Responder` in `main.py`.
- **Use another model provider:** implement `llm/client.LLMClient.complete()`.
