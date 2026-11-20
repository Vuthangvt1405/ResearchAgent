"""The model catalog behind the chat box Model picker."""

import asyncio

from researchchat import llm


def test_catalog_keeps_only_models_that_answer_in_text():
    entries = [
        {"id": "a/chat", "name": "A: Chat", "supported_parameters": ["tools"], "architecture": {"output_modalities": ["text"]}},
        {"id": "b/image", "name": "B: Image", "architecture": {"output_modalities": ["image"]}},
        {"id": "c/plain"},
    ]
    catalog = llm.parse_catalog(entries)
    assert list(catalog) == ["a/chat", "c/plain"]
    assert catalog["a/chat"] == llm.ModelInfo(id="a/chat", name="A: Chat", params=frozenset({"tools"}))
    assert catalog["c/plain"].name == "c/plain"  # a model without a name shows its id


def test_failed_catalog_lookup_is_retried_next_time(monkeypatch):
    class DownClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def get(self, _url: str):
            raise OSError("network down")

    monkeypatch.setattr(llm, "_catalog", None)
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **_kwargs: DownClient())
    assert asyncio.run(llm.model_catalog()) == {}
    assert llm._catalog is None
    assert asyncio.run(llm.model_params("a/chat")) == set()
