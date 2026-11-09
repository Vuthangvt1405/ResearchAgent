"""Load settings from config.toml and .env once, and check them.

Other modules import ready-to-use values from here.
"""

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)

# OpenRouter
OPENROUTER_URL: str = CONFIG["openrouter"]["base_url"]
OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
MODEL: str = os.getenv("OPENROUTER_MODEL") or CONFIG["openrouter"]["model"]

# Chat
SYSTEM_PROMPT: str = CONFIG["chat"]["system_prompt"]
GREETING: str = CONFIG["chat"]["greeting"]

# Thinking effort levels: OpenRouter level -> label shown in the settings panel
ALLOWED_LEVELS = {"default", "off", "minimal", "low", "medium", "high", "xhigh"}


def check_levels(levels: dict[str, str]) -> None:
    """Fail at startup if config.toml names a level OpenRouter doesn't know."""
    unknown = set(levels) - ALLOWED_LEVELS
    if unknown:
        raise ValueError(
            f"config.toml [thinking.levels]: unknown level(s) {sorted(unknown)}. "
            f"Allowed: {sorted(ALLOWED_LEVELS)}"
        )
    if not levels:
        raise ValueError("config.toml [thinking.levels] is empty.")


EFFORT_LEVELS: dict[str, str] = CONFIG["thinking"]["levels"]
check_levels(EFFORT_LEVELS)
EFFORT_DEFAULT: str = CONFIG["thinking"].get("default", "default")
if EFFORT_DEFAULT not in EFFORT_LEVELS:
    EFFORT_DEFAULT = next(iter(EFFORT_LEVELS))

# Web search and page reading
_search = CONFIG.get("web_search", {})
SEARCH_ENABLED: bool = _search.get("enabled", True)
SEARCH_MAX_RESULTS: int = _search.get("max_results", 5)
TOOL_MAX_ROUNDS: int = _search.get("max_rounds", 4)
READ_PAGE_MAX_CHARS: int = _search.get("read_page_max_chars", 8000)

# Notebook workspaces (one notebook, Docker kernel and files folder per project)
_notebook = CONFIG.get("notebook", {})
WORKSPACES_DIR: Path = ROOT / _notebook.get("workspaces_dir", "workspaces")
CELL_TIMEOUT_SECONDS: int = _notebook.get("cell_timeout_seconds", 60)
MAX_OUTPUT_CHARS: int = _notebook.get("max_output_chars", 20000)
MAX_IMAGE_KB: int = _notebook.get("max_image_kb", 1024)
KERNEL_IDLE_MINUTES: int = _notebook.get("kernel_idle_minutes", 30)
MODEL_AUTO_RUN: bool = _notebook.get("model_auto_run", True)
RISKY_CODE_NEEDS_APPROVAL: bool = _notebook.get("risky_code_needs_approval", True)
NOTEBOOK_READ_MAX_CHARS: int = _notebook.get("read_max_chars", 12000)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def check_local_host(host: str) -> None:
    """Refuse to serve the app beyond this PC: anyone who reaches it could run code."""
    if host not in LOCAL_HOSTS:
        raise RuntimeError(
            f"ResearchChat runs notebook code, so it only serves localhost (got host {host!r}). "
            "Start it without --host, or add login first."
        )


_docker = _notebook.get("docker", {})
DOCKER_IMAGE: str = _docker.get("image", "researchchat-kernel:1")
DOCKER_MEMORY: str = _docker.get("memory", "2g")
DOCKER_CPUS: float = _docker.get("cpus", 2)
DOCKER_PIDS_LIMIT: int = _docker.get("pids_limit", 256)
