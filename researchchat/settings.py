"""The chat settings panel (gear icon) and what its values mean for requests."""

from chainlit.input_widget import InputWidget, Select, Switch

from researchchat.config import EFFORT_DEFAULT, EFFORT_LEVELS, SEARCH_ENABLED
from researchchat.workspace.kaggle.account import KaggleAccountStatus
from researchchat.workspace.kaggle.settings_switch import (
    KAGGLE_SWITCH_ID,
    kaggle_switch,
)


def build_widgets(model_params: set[str], kaggle: KaggleAccountStatus) -> list[InputWidget]:
    """Settings to show: what the model supports, then the Kaggle account switch."""
    widgets: list[InputWidget] = []
    if "reasoning" in model_params:
        widgets += [
            Select(
                id="thinking_effort",
                label="Thinking effort",
                # Chainlit items are {label: value}; the panel returns the value.
                items={label: level for level, label in EFFORT_LEVELS.items()},
                initial_value=EFFORT_DEFAULT,
                description="How much the model reasons before answering.",
            ),
            Switch(
                id="show_thinking",
                label="Show thinking",
                initial=True,
                description="Show the model's reasoning above its answer.",
            ),
        ]
    if "tools" in model_params:
        widgets += [
            Switch(
                id="web_search",
                label="Web search",
                initial=SEARCH_ENABLED,
                description="Let the model search the internet and read pages when it needs to.",
            ),
            Switch(
                id="notebook",
                label="Notebook",
                initial=True,
                description="Let the model read your project notebook and run code in it. Risky code asks first.",
            ),
        ]
    widgets.append(kaggle_switch(kaggle))  # shown for every model: connecting needs no model feature
    return widgets


def keep_chat_choices(widgets: list[InputWidget], chosen: dict) -> list[InputWidget]:
    """Start each widget at this chat's own choice, so re-sending Settings keeps what the user picked.

    The Kaggle switch is left as built: it shows the account, which is the same in every chat.
    """
    for widget in widgets:
        if widget.id in chosen and widget.id != KAGGLE_SWITCH_ID:
            widget.initial = chosen[widget.id]
    return widgets


def reasoning_body(settings: dict) -> dict:
    """Build the OpenRouter `reasoning` request field from chat settings."""
    if "thinking_effort" not in settings:  # model has no reasoning support
        return {}
    effort = settings["thinking_effort"]
    if effort == "off":
        return {"reasoning": {"enabled": False}}
    reasoning: dict = {}
    if effort != "default":
        reasoning["effort"] = effort
    if not settings.get("show_thinking", True):
        reasoning["exclude"] = True
    return {"reasoning": reasoning} if reasoning else {}
