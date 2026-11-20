<div align="center">

<!--<img src="asset/snake_logo_pack/snake_logo.svg" alt="SillyTherin logo" width="200" />-->

# SillyTherin

### *If You Are Need Analyst Work Jupyter, I Think Maybe You Need This :D*

**A friendly research assistant that thinks, searches the web, finds datasets and runs notebook code, all from one chat.**

[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Chainlit](https://img.shields.io/badge/built%20with-Chainlit-F80061)](https://chainlit.io)
[![OpenRouter](https://img.shields.io/badge/models-OpenRouter-6566F1)](https://openrouter.ai)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

</div>

---

## Why SillyTherin?

Data analysis usually means jumping between a search engine, dataset sites, download scripts and a Jupyter notebook. SillyTherin puts all of that in one chat. You ask a question, and the assistant researches it on the web, finds and downloads a matching dataset, and analyses it in a notebook you can see. Every step it takes shows up in the chat.

It's for analysts, students and researchers who want to go from a question to working notebook code quickly, without setting everything up by hand.

## Features

- **Thinks before answering:** pick a thinking level and watch the reasoning stream in.
- **Web search:** searches the web and reads public pages, showing every step in the chat.
- **Dataset discovery:** finds datasets on Hugging Face, Zenodo and DataCite.
- **Background downloads:** datasets download while you keep chatting, are verified, and are stored once across projects.
- **Per-project notebook:** each project gets its own notebook and Python kernel in a sandboxed Docker container.
- **Safe by default:** risky code and deletes ask first; only public HTTPS hosts are contacted.
- **Any model on OpenRouter.**

## Quick start

You need **Python 3.11–3.13**, an **[OpenRouter API key](https://openrouter.ai/keys)**, and optionally **Docker** (only for running notebook code).

```bash
git clone https://github.com/Vuthangvt1405/SillyTherin.git
cd SillyTherin
scripts/setup.sh                 # creates .venv, installs packages, creates .env
```

On Windows: `py -3.11 -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`, `copy .env.example .env`.

Add your key to `.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

(Optional) build the notebook kernel with Docker running:

```bash
docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker
```

Run it and open <http://localhost:8000>:

```bash
.venv/bin/chainlit run app.py
```

In the ⚙️ menu next to the message box, turn on **Web search** and **Notebook**.

## Configuration

| File | What |
|---|---|
| `.env` | `OPENROUTER_API_KEY`, optional `OPENROUTER_MODEL` |
| `config.toml` | Model, prompts, search and download limits, thinking levels |
| `.chainlit/config.toml` | Chainlit UI settings |

Restart the app after changing any of these. Projects, notebooks and datasets are stored in `workspaces/` (git-ignored).

> Never start the app with `--host 0.0.0.0`: anyone who can reach it could run code.

## Contributing

Bug reports, ideas and pull requests are welcome.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -m "not docker"    # tests without Docker
ruff check .                                  # lint
```

## License

Licensed under the [Apache License 2.0](LICENSE).

<div align="center">
<sub>Made with ☕ and a slightly silly snake 🐍</sub>
</div>
