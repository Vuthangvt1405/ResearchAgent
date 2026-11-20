<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="public/logo_dark.svg" />
  <img src="public/logo_light.svg" alt="SillyTherin" width="420" />
</picture>

### Build your own dataset from pure curiosity.

A playground for your own data pool, where every question you ask<br />
grows it a little deeper and every answer is yours to explore.

[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/server-FastAPI-009688)](https://fastapi.tiangolo.com)
[![OpenRouter](https://img.shields.io/badge/models-OpenRouter-6566F1)](https://openrouter.ai)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

[Overview](#overview) · [Features](#features) · [Getting started](#getting-started) · [Configuration](#configuration) · [Security](#security) · [Development](#development)

</div>

---

## Overview

Data analysis usually means switching between a search engine, dataset portals, download scripts and a Jupyter notebook. SillyTherin brings these into a single chat. You ask a question; the assistant researches it on the web, finds and downloads a suitable dataset, and analyses it in a notebook that sits beside the conversation. Every step it takes is shown in the chat, so the work stays transparent and reproducible.

SillyTherin is designed for analysts, students and researchers who want to move from an idea to running code quickly, without setting up the tooling by hand.

## Features

| | |
|---|---|
| **Reasoning** | Choose a thinking level per chat and follow the model's reasoning as it streams in. |
| **Web research** | Searches the web and reads public pages, with each search and page shown as a step. |
| **Dataset discovery** | Finds datasets across Hugging Face, Zenodo and DataCite. |
| **Background downloads** | Datasets download while you keep working, are verified on arrival and stored once for reuse across projects. |
| **Project notebooks** | Each project has its own notebook and Python kernel, isolated in a Docker container. The notebook panel offers Jupyter-style cells with syntax highlighting. |
| **Safe defaults** | Risky code and deletions require confirmation, and only public HTTPS hosts are contacted. |
| **Model choice** | Works with any chat model available on OpenRouter. |

## Getting started

### Prerequisites

- **Python** 3.11, 3.12 or 3.13
- An **[OpenRouter API key](https://openrouter.ai/keys)**
- **Docker** (optional, required only to run notebook code)

### Installation

```bash
git clone https://github.com/uV-naloN/SillyTherin.git
cd SillyTherin
scripts/setup.sh    # creates .venv, installs dependencies and creates .env
```

<details>
<summary>Windows</summary>

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

</details>

Add your API key to `.env`:

```dotenv
OPENROUTER_API_KEY=sk-or-...
```

To run notebook code, build the kernel image with Docker running:

```bash
docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker
```

### Running

```bash
.venv/bin/python -m researchchat
```

Open <http://127.0.0.1:8000>. The app is being moved to its own web page: until that page is built, the server runs but shows no chat page (use the `main` branch for the current app).

## Configuration

| File | Purpose |
|---|---|
| `.env` | Secrets: `OPENROUTER_API_KEY`, and optionally `OPENROUTER_MODEL` to override the default model |
| `config.toml` | Default model, system prompt, search and download limits, thinking levels |

Restart the app after changing any of these files. Projects, notebooks and datasets are stored in `workspaces/`, which is excluded from version control.

## Security

SillyTherin executes code, so it only serves `localhost` and refuses to start on any other host. It also refuses requests from any other website open in your browser. Do not expose it on a network (for example with `--host 0.0.0.0`) unless you first add authentication.

## Development

Install the development dependencies, then run the tests and the linter:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -m "not docker"    # tests that do not need Docker
.venv/bin/python -m ruff check .
```

The notebook panel is a separate front-end in `public/panel`:

```bash
cd public/panel
npm ci
npm test
npm run build    # writes the bundle to public/build
```

Contributions are welcome. Please open an issue to discuss larger changes before submitting a pull request.

## License

Released under the [Apache License 2.0](LICENSE).

Built with [FastAPI](https://fastapi.tiangolo.com), [OpenRouter](https://openrouter.ai) and [CodeMirror](https://codemirror.net).
