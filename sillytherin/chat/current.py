"""The chat the running task belongs to, so a tool deep in a turn can reach it.

The server sets it for each chat turn and panel action; outside one, `this_chat()` raises
LookupError (tests and background jobs pass what they need explicitly instead).
"""

from contextvars import ContextVar
from dataclasses import dataclass

from sillytherin.chat.ports import Asker, ChatState, Toaster


@dataclass(frozen=True)
class ChatContext:
    state: ChatState
    asker: Asker
    toaster: Toaster


current_chat: ContextVar[ChatContext] = ContextVar("current_chat")


def this_chat() -> ChatContext:
    return current_chat.get()
