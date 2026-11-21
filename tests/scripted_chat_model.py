"""A LangChain chat model that streams scripted chunks, so tests can drive the agent without OpenRouter."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langsmith.utils import tracing_is_enabled
from pydantic import Field

from sillytherin.agent.history import from_langchain

HANG = object()  # in a script: the stream waits here until the turn is stopped


def text_chunk(text: str) -> AIMessageChunk:
    return AIMessageChunk(content=text)


def reasoning_chunk(text: str) -> AIMessageChunk:
    return AIMessageChunk(content=[{"type": "reasoning", "reasoning": text}])


def tool_call_chunk(name: str, arguments: dict | str, call_id: str = "call-1", index: int = 0) -> AIMessageChunk:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": raw, "id": call_id, "index": index}])


class ScriptedChatModel(BaseChatModel):
    """Answers each call with the next script ("ok" once they run out) and remembers every request."""

    scripts: list[list] = Field(default_factory=list)
    requests: list[dict] = Field(default_factory=list)
    tracing_seen: list[bool] = Field(default_factory=list)  # was LangSmith tracing on during each call

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence, *, tool_choice: str | None = None, **kwargs: object):
        bound = {"tools": [convert_to_openai_tool(tool) for tool in tools], **kwargs}
        if tool_choice is not None:
            bound["tool_choice"] = tool_choice
        return self.bind(**bound)

    def tool_names(self, request_index: int) -> list[str]:
        return [tool["function"]["name"] for tool in self.requests[request_index].get("tools", [])]

    def _generate(self, *_args: object, **_kwargs: object) -> ChatResult:
        raise NotImplementedError("the agent calls the model asynchronously")

    async def _agenerate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: object) -> ChatResult:
        joined: AIMessageChunk | None = None
        async for generation in self._astream(messages, stop, run_manager, **kwargs):
            joined = generation.message if joined is None else joined + generation.message
        return ChatResult(generations=[ChatGeneration(message=joined or AIMessageChunk(content=""))])

    async def _astream(
        self, messages: list[BaseMessage], stop=None, run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: object
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.requests.append({"messages": from_langchain(messages), **kwargs})
        self.tracing_seen.append(tracing_is_enabled())
        for chunk in self.scripts.pop(0) if self.scripts else [text_chunk("ok")]:
            if chunk is HANG:
                await asyncio.Event().wait()
            yield ChatGenerationChunk(message=chunk.model_copy())
