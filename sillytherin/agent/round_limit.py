"""At the round limit the model must answer from what it found, instead of LangGraph stopping with an error."""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelResponse
from langchain.agents.middleware import ModelRequest as AgentCall
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

LIMIT_NOTE = (
    "Tool limit reached. Do not search or read more pages. Answer the user now using the results above, "
    "and cite the URLs you used. Write your answer as plain text; tools can't be used any more."
)


class RoundLimit(AgentMiddleware):
    """Counts this turn's tool rounds; at `max_rounds` the next model call gets the note and no tools."""

    def __init__(self, max_rounds: int) -> None:
        super().__init__()
        self.max_rounds = max_rounds

    async def awrap_model_call(self, request: AgentCall, handler: Callable[[AgentCall], Awaitable[ModelResponse]]) -> ModelResponse:
        if request.tools and tool_rounds_this_turn(request.messages) >= self.max_rounds:
            # the tools stay listed, so the model isn't confused, but can't be called
            request = request.override(tool_choice="none", messages=[*request.messages, SystemMessage(content=LIMIT_NOTE)])
        return await handler(request)


def tool_rounds_this_turn(messages: list[BaseMessage]) -> int:
    """Model answers that called tools since the user's latest message."""
    last_user = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    return sum(1 for m in messages[last_user + 1 :] if isinstance(m, AIMessage) and m.tool_calls)
