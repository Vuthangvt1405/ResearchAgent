"""What OpenRouter offers: its model catalog and each model's capabilities."""

from dataclasses import dataclass

import httpx

from researchchat.config import MODEL, OPENROUTER_URL


@dataclass(frozen=True)
class ModelInfo:
    """One OpenRouter model as the app needs it."""

    id: str
    name: str
    params: frozenset[str]


_catalog: dict[str, ModelInfo] | None = None


async def model_catalog() -> dict[str, ModelInfo]:
    """Every OpenRouter model that answers in text, fetched once per app run."""
    global _catalog
    if _catalog is None:
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(f"{OPENROUTER_URL}/models")
                resp.raise_for_status()
            _catalog = parse_catalog(resp.json()["data"])
        except Exception:
            return {}  # don't cache, so the next chat retries
    return _catalog


def parse_catalog(entries: list[dict]) -> dict[str, ModelInfo]:
    """Keep the models that can write a chat answer; image- or audio-only models can't."""
    return {
        entry["id"]: ModelInfo(
            id=entry["id"],
            name=entry.get("name") or entry["id"],
            params=frozenset(entry.get("supported_parameters", [])),
        )
        for entry in entries
        if answers_in_text(entry)
    }


def answers_in_text(entry: dict) -> bool:
    """Models that don't list their outputs are taken as text models, as most are."""
    outputs = (entry.get("architecture") or {}).get("output_modalities") or ["text"]
    return "text" in outputs


async def model_params(model_id: str = MODEL) -> set[str]:
    """Which request parameters `model_id` supports; none when it is unknown or OpenRouter can't be reached."""
    model = (await model_catalog()).get(model_id)
    return set(model.params) if model else set()
