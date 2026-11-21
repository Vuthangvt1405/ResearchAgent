"""The OpenRouter chat model for one message, with that message's model and thinking settings."""

from dataclasses import dataclass

from langchain_openrouter import ChatOpenRouter

from researchchat.config import OPENROUTER_API_KEY

APP_TITLE = "SillyTherin"  # how OpenRouter names the app on the account's activity page


@dataclass(frozen=True)
class ModelRequest:
    """How every round of one turn calls the model."""

    model: str  # OpenRouter model id
    tools: list[dict]  # tool DEFINITIONs the model may call this turn
    thinking: dict  # reasoning_body(): {"reasoning": {...}} or {} for a model that doesn't think


def build_chat_model(request: ModelRequest) -> ChatOpenRouter:
    """The model for one message; no app URL is sent, so OpenRouter only learns the app's name."""
    return ChatOpenRouter(
        model=request.model,
        streaming=True,
        reasoning=request.thinking.get("reasoning"),
        openrouter_api_key=OPENROUTER_API_KEY,
        app_title=APP_TITLE,
        app_url=None,
    )
