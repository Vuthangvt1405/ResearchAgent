"""The chat settings panel and what its values mean for requests."""

from dataclasses import replace

from researchchat.chat.widgets import SettingSwitch
from researchchat.config import SEARCH_ENABLED
from researchchat.workspace.kaggle.account import KaggleAccountStatus
from researchchat.workspace.kaggle.settings_switch import (
    KAGGLE_SWITCH_ID,
    kaggle_switch,
)

SHOW_THINKING_ID = "show_thinking"
WEB_SEARCH_ID = "web_search"
NOTEBOOK_ID = "notebook"
NO_REASONING_REASON = "This model doesn't think before answering."
NO_TOOLS_REASON = "This model can't use tools."


def build_widgets(model_params: set[str], kaggle: KaggleAccountStatus) -> list[SettingSwitch]:
    """Settings in reading order: Answers, Tools, then the Kaggle account."""
    # Kaggle is shown for every model: connecting needs no model feature
    return answer_widgets(model_params) + tool_widgets(model_params) + [kaggle_switch(kaggle)]


def answer_widgets(model_params: set[str]) -> list[SettingSwitch]:
    """The Answers group: Show thinking, greyed with a reason when the model doesn't reason."""
    can_reason = "reasoning" in model_params
    return [
        SettingSwitch(
            id=SHOW_THINKING_ID,
            label="Show thinking",
            initial=can_reason,
            disabled=not can_reason,
            description="Show the model's reasoning above its answer." if can_reason else NO_REASONING_REASON,
        )
    ]


def tool_widgets(model_params: set[str]) -> list[SettingSwitch]:
    """The Tools group: Web search and Notebook, greyed with a reason when the model can't use tools."""
    can_use_tools = "tools" in model_params
    return [
        SettingSwitch(
            id=WEB_SEARCH_ID,
            label="Web search",
            initial=SEARCH_ENABLED and can_use_tools,
            disabled=not can_use_tools,
            description="Let the model search the internet and read pages when it needs to." if can_use_tools else NO_TOOLS_REASON,
        ),
        SettingSwitch(
            id=NOTEBOOK_ID,
            label="Notebook",
            initial=can_use_tools,
            disabled=not can_use_tools,
            description=(
                "Let the model read your project notebook and run code in it. Risky code asks first."
                if can_use_tools
                else NO_TOOLS_REASON
            ),
        ),
    ]


def keep_chat_choices(widgets: list[SettingSwitch], chosen: dict) -> list[SettingSwitch]:
    """Start each widget at this chat's own choice, so re-sending Settings keeps what the user picked.

    The Kaggle switch is left as built: it shows the account, which is the same in every chat.
    Greyed rows are left as built too: a feature the model lacks stays off whatever was picked before.
    """
    return [replace(widget, initial=chosen[widget.id]) if keeps_choice(widget, chosen) else widget for widget in widgets]


def keeps_choice(widget: SettingSwitch, chosen: dict) -> bool:
    return widget.id in chosen and widget.id != KAGGLE_SWITCH_ID and not widget.disabled


def reasoning_body(effort: str, show_thinking: bool, can_reason: bool) -> dict:
    """Build the OpenRouter `reasoning` request field from the Effort pick and the Show thinking switch."""
    if not can_reason:
        return {}
    if effort == "off":
        return {"reasoning": {"enabled": False}}
    reasoning: dict = {}
    if effort != "default":
        reasoning["effort"] = effort
    if not show_thinking:
        reasoning["exclude"] = True
    return {"reasoning": reasoning} if reasoning else {}


def usable_settings(settings: dict, model_params: set[str]) -> dict:
    """The chat's settings with switches the model can't use turned off, so no tools go to a model without tools."""
    if "tools" in model_params:
        return settings
    return {**settings, WEB_SEARCH_ID: False, NOTEBOOK_ID: False}
