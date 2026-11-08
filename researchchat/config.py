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
