# ResearchChat

A research assistant chatbot built with [Chainlit](https://chainlit.io) on
[OpenRouter](https://openrouter.ai). It can think before answering, search the
web, and read pages, showing each step in the chat.

## Setup

You need:
- **Python 3.11, 3.12 or 3.13.** Python 3.14 doesn't work with Chainlit yet.
  If you don't have one, [uv](https://docs.astral.sh/uv/) can install it
  without touching your system Python: `uv python install 3.11`.
- **An OpenRouter API key** from https://openrouter.ai/keys.
- **Optional: Docker**, only for running notebook code. Chat, search and
  dataset downloads work without it.

### Linux / macOS

```bash
scripts/setup.sh
```

The script finds a supported Python (including one installed by uv), creates
`.venv`, installs the packages and creates `.env` from `.env.example`. It's
safe to run again. Then put your key in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

### Windows

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then put your OpenRouter key in .env
```

### Notebook code (optional)

Build the kernel image once, with Docker running:

```bash
docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker
```

## Run

```bash
.venv/bin/chainlit run app.py          # Windows: .venv\Scripts\chainlit run app.py
```

Then open http://localhost:8000. In the gear menu next to the message box,
turn on **Web search** and **Notebook** to give the assistant its tools.

If the Python version is wrong or the API key is missing, the app stops at
start with a message saying what to fix.

## Test

```bash
.venv/bin/python -m pytest -m "not docker"     # everything except the Docker kernel tests
.venv/bin/python -m pytest                     # all, with Docker running and the image built
```

The tests need no API key or network.

## Configure

| Where | What |
|---|---|
| `.env` | `OPENROUTER_API_KEY` (secret), optional `OPENROUTER_MODEL` override |
| `config.toml` | Model, system prompt, greeting, web and dataset search limits, dataset download limits (`[datasets]`), thinking levels and their labels |
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
    dataset_search.py       Find datasets (Hugging Face, Zenodo, DataCite), merged and ranked
    notebook_run.py         Run code in the project notebook (risky code asks first)
    notebook_read.py        Let the model read the project notebook
    dataset_download.py     Download a dataset into the project in the background
    dataset_list.py         The project's datasets, with status and paths
    dataset_delete.py       Delete a dataset (always asks you first)
  workspace/                Project notebooks (in progress, see below)
    store.py                Projects and .ipynb files on disk
    kernels.py              One Docker kernel container per project
    risk.py                 Flags risky model code
    service.py              Edits and runs notebooks under a per-project lock
    datasets_store.py       datasets.json, dataset ids and safe paths on disk
    dataset_sources.py      Hugging Face / Zenodo file lists and safe HTTPS downloads
    dataset_service.py      Download queue, checks, delete/cancel, chat notes
    dataset_pool.py         Shared dataset pool: index, links, cleanup, NB-3 migration
    panel.py                The right-side Notebook panel
    actions.py              Buttons the panel calls
public/
  elements/Notebook.jsx     The Notebook panel UI
  custom.js                 Project picker (pill) inside the message box
docker/kernel.Dockerfile    The notebook kernel image
tests/                      pytest tests
```

### Notebook workspace (in progress)

Each project gets one notebook, one Python kernel and one `files/` folder,
stored in `workspaces/<project>/` (git-ignored). The plan is in
`docs/plans/done/notebook-workspace-plan.md`; right now only the skeleton exists.

- Code runs in a **Docker container** per project, so Docker Desktop must be
  running. Build the kernel image once:
  `docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker`
- The container can reach the internet but only sees the project's `files/`
  folder (as `/work`) and none of your environment variables.
- Never start the app with `--host 0.0.0.0`: anyone who can reach it could run
  code. The app will refuse a non-local host.
- Kernel tests are marked `docker`; run the rest with `pytest -m "not docker"`.

### Dataset downloads

With the Notebook switch on, the assistant can download a Hugging Face or
Zenodo dataset it found with `dataset_search` into the current project
(`dataset_download`). The plan is in `docs/plans/done/NB-3-dataset-download-plan.md`.

- Downloads run **in the background**: you keep chatting, the panel's
  Datasets section shows progress, and the chat gets a message when it's ready.
  Notebook code reads the files from `/work/datasets/<id>/`.
- Before starting, the app checks the disk has room (counting downloads already
  queued). Downloads over `ask_above_mb` (default 200 MB) ask Download / Skip.
- Files are verified (size and md5/sha256) before they're moved in; failed or
  cancelled downloads leave no partial files. Only public HTTPS hosts are
  contacted, and no tokens are sent, so gated or private datasets are refused.
- An existing dataset keeps its version unless you ask the assistant to update
  it. Asking again downloads only files the project doesn't have yet.
- `[datasets]` in `config.toml` sets the limits: `min_free_disk_mb`,
  `ask_above_mb`, `max_files`, `parallel_downloads` (app-wide) and
  `stall_timeout_seconds`.


### Shared dataset pool

Downloaded data is stored once and shared by every project. The plan is in
`docs/plans/done/NB-4-dataset-pool-plan.md`.

- The bytes live in `workspaces/.dataset-pool/<dataset>@<revision>/`, listed in
  `workspaces/.dataset-pool.json`. A project's `files/datasets/<id>/` holds
  relative links into it, so `/work/datasets/<id>/...` paths work the same
  in notebook code, and a dataset another project already has is ready at once.
- Kernels see the pool read-only: to change a file, copy it elsewhere in `/work`
  first. Removing a link from `/work/datasets/` only makes the dataset show as
  missing; asking for it again links it back without downloading.
- Two projects asking for the same files at once share one download; cancelling
  stops it for that project only.
- Delete removes a dataset from one project. Its files go when no project uses
  it any more; until then the panel says which other projects still use it.
- A project keeps its version until you ask to update it; then only that project
  moves to the new version.
- Datasets downloaded before this (NB-3) are moved into the pool on the first
  start; the old `datasets.json` is kept as `datasets.json.v1`.

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
