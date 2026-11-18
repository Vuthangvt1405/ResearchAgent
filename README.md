<div align="center">

<img src="asset/logo.png" alt="SillyTherin logo" width="200" />

# SillyTherin

### *If You Are Need Analyst Work Jupyter, I Think Maybe You Need This :D*

**A friendly research assistant that thinks, searches the web, finds datasets and runs notebook code, all from one chat.**

[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Chainlit](https://img.shields.io/badge/built%20with-Chainlit-F80061)](https://chainlit.io)
[![OpenRouter](https://img.shields.io/badge/models-OpenRouter-6566F1)](https://openrouter.ai)
[![Docker](https://img.shields.io/badge/notebook-Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-contributing)

[Features](#features) · [Quick start](#quick-start) · [Configuration](#-configuration) · [How it works](#-how-it-works) · [Contributing](#-contributing)

</div>

---

## Features

- **Thinks before answering:** pick a thinking level and watch the reasoning stream into its own step.
- **Web search and page reading:** searches the web (DuckDuckGo) and reads public pages, showing every step in the chat.
- **Dataset discovery:** finds datasets on Hugging Face, Zenodo and DataCite, merged and ranked.
- **Background dataset downloads:** downloads run while you keep chatting, are checked (size + md5/sha256) and shared between projects, so each dataset is stored once.
- **Per-project notebook:** every project gets its own notebook and Python kernel in a sandboxed Docker container, plus a side panel to see it.
- **Safe by default:** risky code asks before it runs, deletes always ask, only public HTTPS hosts are contacted, and a project's kernel can read only its own datasets.
- **Any model on OpenRouter:** the settings panel only shows what the chosen model supports.

## Quick start

### Requirements

- **Python 3.11, 3.12 or 3.13** (3.14 doesn't work with Chainlit yet). No suitable Python? [uv](https://docs.astral.sh/uv/) can install one without touching your system Python: `uv python install 3.11`.
- **An OpenRouter API key** from <https://openrouter.ai/keys>.
- **Docker** *(optional)*, only needed to run notebook code. Chat, search and dataset downloads work without it.

### 1. Install

**Linux / macOS**

```bash
git clone https://github.com/Vuthangvt1405/SillyTherin.git
cd SillyTherin
scripts/setup.sh
```

The script finds a supported Python (including one installed by uv), creates `.venv`, installs the packages and creates `.env` from `.env.example`. It's safe to run again.

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### 2. Add your API key

Put your key in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

### 3. (Optional) Build the notebook kernel

With Docker running:

```bash
docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker
```

### 4. Run

```bash
.venv/bin/chainlit run app.py          # Windows: .venv\Scripts\chainlit run app.py
```

Open <http://localhost:8000>. In the ⚙️ menu next to the message box, turn on **Web search** and **Notebook** to give the assistant its tools.

> If the Python version is wrong or the API key is missing, the app stops at start with a message saying what to fix.

## 🔧 Configuration

| Where | What |
|---|---|
| `.env` | `OPENROUTER_API_KEY` (secret), optional `OPENROUTER_MODEL` override |
| `config.toml` | Model, system prompt, greeting, web and dataset search limits, dataset download limits (`[datasets]`), thinking levels and their labels |
| `.chainlit/config.toml` | Chainlit UI settings (app name, theme, features) |
| `chainlit.md` | The Readme page shown in the app |

Restart the app after changing any of these.

The settings panel only shows what the model supports: thinking options need `reasoning`, and the web search switch needs `tools`, according to OpenRouter's model list.

## 🧩 How it works

### How a message flows

1. `on_message` adds your message to the chat history.
2. `stream_round` sends the history to OpenRouter and streams back thinking (into a "Thinking" step) and the answer (into the reply).
3. If the model calls tools, `run_tool_call` runs each one in its own step and adds the results to the history, then the model gets another round.
4. After `max_rounds` tool rounds, the model is told to answer with what it has.

### Notebook workspace

Each project gets one notebook, one Python kernel and one `files/` folder, stored in `workspaces/<project>/` (git-ignored). Plan: `docs/plans/done/notebook-workspace-plan.md`.

- Code runs in a **Docker container** per project, so Docker must be running.
- The container can reach the internet but only sees the project's `files/` folder (as `/work`) and none of your environment variables.
- **Never start the app with `--host 0.0.0.0`:** anyone who can reach it could run code. The app refuses a non-local host.

### Dataset downloads

With the Notebook switch on, the assistant can download a Hugging Face or Zenodo dataset it found with `dataset_search` into the current project (`dataset_download`). Plan: `docs/plans/done/NB-3-dataset-download-plan.md`.

- Downloads run **in the background**: you keep chatting, the panel's Datasets section shows progress, and the chat gets a message when it's ready. Notebook code reads the files from `/work/datasets/<id>/`.
- Before starting, the app checks the disk has room (counting downloads already queued). Downloads over `ask_above_mb` (default 200 MB) ask Download / Skip.
- Files are verified (size and md5/sha256) before they're moved in; failed or cancelled downloads leave no partial files. Only public HTTPS hosts are contacted and no tokens are sent, so gated or private datasets are refused.
- An existing dataset keeps its version unless you ask the assistant to update it. Asking again downloads only files the project doesn't have yet.
- `[datasets]` in `config.toml` sets the limits: `min_free_disk_mb`, `ask_above_mb`, `max_files`, `parallel_downloads` (app-wide) and `stall_timeout_seconds`.

### Shared dataset pool

Downloaded data is stored once and shared by every project. Plan: `docs/plans/done/NB-4-dataset-pool-plan.md`.

- The bytes live in `workspaces/.dataset-pool/<dataset>@<revision>/`, listed in the database (`pool_entries`, `pool_files`). A project's `files/datasets/<id>/` holds relative links into it, so `/work/datasets/<id>/...` paths work the same in notebook code, and a dataset another project already has is ready at once.
- Kernels see the pool read-only: to change a file, copy it elsewhere in `/work` first. Removing a link from `/work/datasets/` only makes the dataset show as missing; asking for it again links it back without downloading.
- Two projects asking for the same files at once share one download; cancelling stops it for that project only.
- Delete removes a dataset from one project. Its files go when no project uses it any more; until then the panel says which other projects still use it.
- A project keeps its version until you ask to update it; then only that project moves to the new version.

### Where your data lives

Projects, each project's datasets and the shared pool index are stored in one SQLite file, `workspaces/researchchat.db` (name set by `[notebook] database_file`). Notebooks (`notebook.ipynb`), project files and pooled dataset files stay ordinary files in `workspaces/`. Kernels never see the database: they only get the project's `files/` and the read-only pool. Plan: `docs/plans/sqlite-alembic-storage-plan.md`.

- The app creates the database on first start and applies new migrations on every start. A damaged file, or one made by a newer version, stops the app with a message saying what to do.
- **Upgrading from an older checkout:** the old JSON files (`project.json`, `datasets.json`, `.dataset-pool.json`) aren't read any more. Delete the contents of `workspaces/` (copy out any notebook you want to keep) and start the app; it begins with an empty `Default` project.

## 🗂️ Project layout

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
  db/                       The app's SQLite database (see "Where your data lives")
    schema.py               Table definitions (SQLAlchemy Core), read by Alembic
    engine.py               Opens workspaces/researchchat.db and upgrades it on start
    migrations/             Alembic migrations (versions/0001_initial_schema.py, ...)
  workspace/                Project notebooks
    store.py                Projects (database rows) and their .ipynb files on disk
    kernels.py              One Docker kernel container per project
    risk.py                 Flags risky model code
    service.py              Edits and runs notebooks under a per-project lock
    datasets/               Everything about a project's datasets
      store.py              Project datasets (database rows), dataset ids and safe paths
      sources.py            Hugging Face / Zenodo file lists and safe HTTPS downloads
      service.py            Download queue, checks, delete/cancel, chat notes
      pool.py               Shared dataset pool: index (database rows), links, cleanup
      created.py            Data files created in the notebook, listed as datasets
      created_store.py      Database rows for those created files
    panel.py                The right-side Notebook panel
    actions.py              Buttons the panel calls
public/
  elements/Notebook.jsx     The Notebook panel UI
  custom.js                 Project picker (pill) inside the message box
docker/kernel.Dockerfile    The notebook kernel image
alembic.ini                 Alembic CLI config (schema migrations)
asset/logo.png              The SillyTherin logo
tests/                      pytest tests
```

## 🤝 Contributing

Contributions are welcome! Bug reports, ideas and pull requests all help.

1. Fork the repo and create a branch: `git checkout -b feat/my-change`
2. Install the dev tools and run the checks (see below).
3. Open a pull request describing what changed and why.

### Running the tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt   # once: adds ruff (lint) and vulture (dead-code scan)
.venv/bin/python -m pytest -m "not docker"                # everything except the Docker kernel tests
.venv/bin/python -m pytest                                # all, with Docker running and the image built
ruff check .                                              # lint
vulture                                                   # dead-code scan
```

The tests need no API key or network.

### Adding a tool

1. Create `researchchat/tools/my_tool.py` with:
   - `DEFINITION`: the OpenAI-style function schema the model sees
   - `step_title(args) -> str`: the title of its chat step
   - `async run(args) -> (shown, result)`: text for the chat step, and the result sent back to the model
2. Add it to `_MODULES` in `researchchat/tools/__init__.py`.

### Changing the database schema

The schema is managed by [Alembic](https://alembic.sqlalchemy.org/). Edit the tables in `researchchat/db/schema.py`, then from the repo root:

```bash
alembic revision --autogenerate --rev-id 0002 -m "describe the change"
alembic upgrade head
```

To run them on another file than `workspaces/researchchat.db`, add `-x database=path/to/file.db` (e.g. `alembic -x database=/tmp/try.db upgrade head`). Review the generated file in `researchchat/db/migrations/versions/` before committing it (SQLite changes run in Alembic's batch mode). The app also runs `upgrade head` itself on start, and `tests/test_database.py` checks that the migrations match `schema.py`.

## 🙏 Acknowledgements

SillyTherin stands on the shoulders of [Chainlit](https://chainlit.io), [OpenRouter](https://openrouter.ai), [Jupyter](https://jupyter.org/), [SQLAlchemy](https://www.sqlalchemy.org/) / [Alembic](https://alembic.sqlalchemy.org/), [ddgs](https://pypi.org/project/ddgs/), and the open data on [Hugging Face](https://huggingface.co/datasets), [Zenodo](https://zenodo.org/) and [DataCite](https://datacite.org/).

## 📄 License

No license has been chosen yet. Until a `LICENSE` file is added, all rights are reserved by the author.

<div align="center">
<sub>Made with ☕ and a slightly silly snake 🐍</sub>
</div>
