"""Streams one agent run into the chat: thinking into the work group, text into the answer."""

from langchain_core.messages import AIMessageChunk, BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langsmith.run_helpers import tracing_context

from researchchat.chat.ports import AnswerView, ThinkingStep
from researchchat.progress import Progress

RECURSION_SAFETY_NET = 200  # LangGraph's own step limit; the round limit always answers well before it
WRITING_LABEL = "Writing answer"


class RoundView:
    """What one model call has shown so far: its Thinking step, and whether its text has started."""

    def __init__(self, answer: AnswerView, progress: Progress) -> None:
        self.answer = answer
        self.progress = progress
        self.message_id: str | None = None
        self.thinking: ThinkingStep | None = None
        self.has_text = False

    async def show(self, chunk: AIMessageChunk) -> None:
        if chunk.id != self.message_id:
            await self.close_thinking()
            self.message_id, self.has_text = chunk.id, False
        for block in chunk.content_blocks:
            if block["type"] == "reasoning" and block.get("reasoning"):
                await self.think(block["reasoning"])
            elif block["type"] == "text" and block.get("text"):
                await self.write(block["text"])
            elif block["type"] == "tool_call_chunk":
                await self.close_thinking()

    async def think(self, text: str) -> None:
        if self.thinking is None:
            self.thinking = await self.progress.start_thinking()
        await self.thinking.stream(text)

    async def write(self, text: str) -> None:
        await self.close_thinking()
        if not self.has_text and self.progress.is_open:
            await self.progress.now(WRITING_LABEL)
        self.has_text = True
        await self.answer.stream(text)

    async def close_thinking(self) -> None:
        if self.thinking is not None:
            await self.thinking.close()
            self.thinking = None


async def stream_agent(agent: CompiledStateGraph, messages: list[BaseMessage], answer: AnswerView, progress: Progress) -> list[BaseMessage]:
    """Run the agent on `messages`; returns the messages the run added (tool calls, tool results, the answer)."""
    view = RoundView(answer, progress)
    added: list[BaseMessage] = []
    try:
        # Conversations go only to OpenRouter, even if LangSmith tracing is switched on in the environment
        with tracing_context(enabled=False):
            async for mode, data in agent.astream(
                {"messages": messages}, stream_mode=["messages", "updates"], config={"recursion_limit": RECURSION_SAFETY_NET}
            ):
                if mode == "messages" and isinstance(data[0], AIMessageChunk):
                    await view.show(data[0])
                elif mode == "updates":
                    added.extend(messages_in(data))
    finally:
        await view.close_thinking()
    return added


def messages_in(update: dict) -> list[BaseMessage]:
    """The messages each node of the agent added in one step."""
    found: list[BaseMessage] = []
    for node_update in update.values():
        if isinstance(node_update, dict):
            found.extend(node_update.get("messages", []))
    return found
