"""What a chat starts with, and the pickers and Settings it shows for its model."""

from researchchat.chat.ports import ChatState, SettingsView
from researchchat.chat.widgets import Picker, SettingSwitch
from researchchat.config import EFFORT_DEFAULT, EFFORT_LEVELS, MODEL, SYSTEM_PROMPT
from researchchat.llm import ModelInfo, model_catalog, model_params
from researchchat.modes import PickerChoices, Picks, build_modes, picker_models
from researchchat.settings import build_widgets, keep_chat_choices
from researchchat.workspace.kaggle.account import KaggleAccountStatus

HISTORY_KEY = "history"
PICKS_KEY = "picks"
SETTINGS_KEY = "settings"

DEFAULT_PICKS = Picks(model=MODEL, effort=EFFORT_DEFAULT)
ABILITY_LABELS = (("reasoning", "thinks"), ("tools", "tools"))  # OpenRouter parameter -> picker wording


def start_chat_values(chat: ChatState) -> None:
    """A new chat: only the system prompt in its history, and the default picks."""
    chat.set(HISTORY_KEY, [{"role": "system", "content": SYSTEM_PROMPT}])
    chat.set(PICKS_KEY, DEFAULT_PICKS)


def current_picks(chat: ChatState) -> Picks:
    """This chat's Model and Effort picks, or the defaults before its first message."""
    picks = chat.get(PICKS_KEY)
    return picks if isinstance(picks, Picks) else DEFAULT_PICKS


async def picker_choices() -> PickerChoices:
    """What the pickers offer: every OpenRouter text model, and the configured effort levels."""
    catalog = await model_catalog()
    names = {model.id: model.name for model in catalog.values()}
    return PickerChoices(models=picker_models(names, MODEL), levels=EFFORT_LEVELS, model_details=model_details(catalog))


def model_details(models: dict[str, ModelInfo]) -> dict[str, str]:
    """Model id -> what it can do ("thinks · tools", "thinks", "tools" or ""), shown in the Model picker."""
    return {model_id: model_abilities(model.params) for model_id, model in models.items()}


def model_abilities(params: frozenset[str]) -> str:
    abilities = [label for param, label in ABILITY_LABELS if param in params]
    return " · ".join(abilities)


async def pickers_for(picks: Picks) -> list[Picker]:
    """The chat box pickers at these picks; Effort only when the model can reason."""
    can_reason = "reasoning" in await model_params(picks.model)
    return build_modes(await picker_choices(), picks, can_reason)


async def switches_for(chat: ChatState, kaggle: KaggleAccountStatus) -> list[SettingSwitch]:
    """The Settings rows for this chat's model, with the Kaggle switch in `kaggle`'s state."""
    return build_widgets(await model_params(current_picks(chat).model), kaggle=kaggle)


async def opening_controls(chat: ChatState, kaggle: KaggleAccountStatus) -> tuple[list[Picker], list[SettingSwitch]]:
    """The pickers and Settings a new chat shows first; the switches' start values become its settings."""
    switches = await switches_for(chat, kaggle)
    chat.set(SETTINGS_KEY, {switch.id: switch.initial for switch in switches})
    return await pickers_for(current_picks(chat)), switches


async def follow_model_change(chat: ChatState, view: SettingsView, kaggle: KaggleAccountStatus) -> None:
    """A new model can change what the chat offers: re-send the pickers and Settings for it."""
    await view.show_pickers(await pickers_for(current_picks(chat)))
    chosen = chat.get(SETTINGS_KEY) or {}
    switches = keep_chat_choices(await switches_for(chat, kaggle), chosen)
    chat.set(SETTINGS_KEY, await view.show_settings(switches))
