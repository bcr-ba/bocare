# Desktop client

PyQt6 window for BoCare. It contains no medical logic: it sends messages to the backend's `POST /chat/stream` and displays what comes back. Run it with `python -m desktop.main` from the repository root, with the backend running (see [SETUP.md](../SETUP.md)).

## What it shows

- The **triage card as soon as the backend sends it** (under half a second): urgency level, recommendation, safety messages, then progress ("checking the answer… 12 s").
- The **verified answer** once it arrives: explanations with clickable citation numbers, warning signs, self-care, a clarifying question, follow-up questions, sources, disclaimer.
- In the header: the session's urgency level and whether the server and model are reachable.
- If the server can't be reached: an error message with a button to send the last message again.

## Files

| File | Contents |
|---|---|
| `main.py` | Entry point |
| `ui_main.py` | Main window: header, chat, composer, menus, request threads |
| `widgets.py` | Message rows, triage panel, answer card, pending card, input box |
| `api_client.py` | HTTP client, including the server-sent-events reader |
| `theme.py` | Maps an urgency level to its visual severity |
| `config_loader.py` | Loads and validates `config/` |
| `config/settings.yml` | API address, timeouts, window and bubble sizes, urgency colour thresholds |
| `config/strings.yml` | Every text, in French and English (validated to have the same keys) |
| `config/theme.yml` | Colours |
| `config/style.qss` | Qt stylesheet; `$name` placeholders are colours from `theme.yml` |

`BOCARE_API_URL` in the environment overrides `api_url` in `settings.yml`.

## Keyboard

Enter sends, Shift+Enter adds a new line, Ctrl+N starts a new consultation, Ctrl+E exports it as JSON.

## Tests

`pytest desktop/tests` runs the UI offscreen (no window opens): card layout, triage-first display while streaming, citation links, the input counter, the event-stream parser.
