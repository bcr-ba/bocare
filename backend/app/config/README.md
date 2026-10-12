# Configuration

Everything BoCare *does*, as opposed to how it does it, is set in the YAML files of this folder and of [`../prompts/`](../prompts/). Each file has a schema in [`../schemas/config.py`](../schemas/config.py) and is checked when the server starts: a missing value, a missing translation, a regex that doesn't compile or a reference to an unknown specialist stops the server with the file and field named.

After editing a file, restart the server and run `pytest`.

## Files

| File | Controls | Read by |
|---|---|---|
| `settings.yml` | Models, timeouts, judge, corpus and index, embedding model, session storage and retention, tracing, rate limit, log level | `core/settings.py` |
| `triage.yml` | Red flags (level 5), symptom profiles, urgency keywords, logging threshold | `pipeline/triage.py` |
| `care_paths.yml` | Advice and timeframe for each level, specialists | `pipeline/triage.py` |
| `follow_up_questions.yml` | Follow-up questions and when to stop asking | `pipeline/follow_up.py` |
| `safety.yml` | Input length limits, injection patterns, self-harm and medication keywords, their messages | `pipeline/safety.py` |
| `verification.yml` | Delay-advice, dose and diagnostic-certainty patterns | `pipeline/verifier.py` |
| `conversation.yml` | Small-talk patterns and replies, disclaimer, fallback and error texts, output clean-up | `pipeline/orchestrator.py`, `preprocessor.py`, `postprocessor.py` |
| `medical_terms.yml` | French/English symptom phrases mapped to English MedlinePlus search terms | `retrieval/query_terms.py` |
| `../prompts/answer.yml` | System prompt, urgent-case rule, retry note, source format | `llm/prompts.py` |
| `../prompts/judge.yml` | Judge prompt | `llm/prompts.py` |

## Settings vs. data

`settings.yml` holds values that differ between machines (model name, timeouts). Each key can be **overridden by an environment variable** or the `.env` file with the same name in upper case, for example `JUDGE_MIN_LEVEL=4`. Secrets such as `OPENROUTER_API_KEY` belong in `.env` only.

The other files hold the clinical and conversational content. They're the same everywhere and have no environment override: change them in the file, with a review.

## Editing safely

- **Triage and safety files are clinical content.** Changes there change what patients are told to do. Have them reviewed, and add a test case in `backend/tests/` for every rule you add or change.
- **Matching:** `triage.yml`, `safety.yml` and the keyword lists are case-insensitive substring matches on the message. `medical_terms.yml` matches whole words with an optional plural "s".
- **Regex fields** (`injection_patterns`, `verification.yml`, `small_talk` patterns, `output_cleanup`) are Python regular expressions. In YAML, put them in single quotes when they contain `:` or start with a special character.
- **Placeholders** in braces (`{advice}`, `{level}`, `{max_length}`) are filled in by the code; literal braces in prompts are doubled (`{{ }}`).
- **Every text must exist in French and English**, with the same number of follow-up questions in each.
