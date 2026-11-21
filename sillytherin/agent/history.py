"""A chat's history (plain dicts, as the rest of the app reads it) to LangChain messages and back."""

import json
from collections.abc import Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def to_langchain(history: list[dict]) -> list[BaseMessage]:
    return [MESSAGE_FROM_ROLE[entry["role"]](entry) for entry in history]


def from_langchain(messages: list[BaseMessage]) -> list[dict]:
    return [as_dict(message) for message in messages]


def tool_calls_from_dicts(calls: list[dict]) -> list[dict]:
    return [{"name": c["function"]["name"], "args": parse_arguments(c["function"]["arguments"]), "id": c["id"]} for c in calls]


def parse_arguments(arguments: str) -> dict:
    """The app has always run a tool with no arguments when they aren't valid JSON."""
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def assistant_message(entry: dict) -> AIMessage:
    return AIMessage(content=entry.get("content") or "", tool_calls=tool_calls_from_dicts(entry.get("tool_calls", [])))


MESSAGE_FROM_ROLE: dict[str, Callable[[dict], BaseMessage]] = {
    "system": lambda entry: SystemMessage(content=entry["content"]),
    "user": lambda entry: HumanMessage(content=entry["content"]),
    "assistant": assistant_message,
    "tool": lambda entry: ToolMessage(content=entry["content"], tool_call_id=entry["tool_call_id"]),
}


def as_dict(message: BaseMessage) -> dict:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.text}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.text}
    if isinstance(message, ToolMessage):
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.text}
    if isinstance(message, AIMessage) and message.tool_calls:
        calls = [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
            for c in message.tool_calls
        ]
        return {"role": "assistant", "content": message.text or None, "tool_calls": calls}
    return {"role": "assistant", "content": message.text}
