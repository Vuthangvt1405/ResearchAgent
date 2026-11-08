# ResearchChat

A research assistant chatbot built with [Chainlit](https://chainlit.io) on
[OpenRouter](https://openrouter.ai). It can think before answering, search the
web, and read pages, showing each step in the chat.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then put your OpenRouter key in .env
```

## Run

```bash
chainlit run app.py
```

Then open http://localhost:8000.

> **Python 3.14:** Chainlit's CLI applies `nest_asyncio`, which breaks on 3.14
> (every page request fails with "Not currently running on any asynchronous
> event loop"). Use Python 3.11–3.13, or start it with the workaround in
> `.claude/launch.json`.

## Test

```bash
python -m pytest
```

The tests need no API key or network.

## Configure

| Where | What |
|---|---|
| `.env` | `OPENROUTER_API_KEY` (secret), optional `OPENROUTER_MODEL` override |
| `config.toml` | Model, system prompt, greeting, web search limits, thinking levels and their labels |
| `.chainlit/config.toml` | Chainlit UI settings (app name, theme, features) |
| `chainlit.md` | The Readme page shown in the app |

Restart the app after changing any of these.

The settings panel (gear icon next to the message box) only shows what the
model supports: thinking options need `reasoning`, the web search switch
needs `tools`, according to OpenRouter's model list.

## Project layout

```
app.py                      Chainlit hooks: chat start, settings, the message/tool loop
researchchat/
  config.py                 Loads config.toml + .env once and checks them
  llm.py                    OpenRouter client, model capabilities, streaming
  settings.py               Settings panel widgets and the `reasoning` request field
  tools/
    __init__.py             Tool list and run_tool_call (runs a tool in a chat step)
    web_search.py           Search the web (DuckDuckGo via ddgs)
    read_page.py            Read a public web page (local/private addresses blocked)
tests/                      pytest tests
```

### How a message flows

1. `on_message` adds your message to the chat history.
2. `stream_round` sends the history to OpenRouter and streams back thinking
   (into a "Thinking" step) and the answer (into the reply).
3. If the model calls tools, `run_tool_call` runs each one in its own step and
   adds the results to the history, then the model gets another round.
4. After `max_rounds` tool rounds, the model is told to answer with what it has.

### Adding a tool

1. Create `researchchat/tools/my_tool.py` with:
   - `DEFINITION`: the OpenAI-style function schema the model sees
   - `step_title(args) -> str`: the title of its chat step
   - `async run(args) -> (shown, result)`: text for the chat step, and the
     result sent back to the model
2. Add it to `_MODULES` in `researchchat/tools/__init__.py`.
