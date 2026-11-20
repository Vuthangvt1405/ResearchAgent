"""The Model and Effort pickers in the chat box, and reading what a message chose."""

from dataclasses import dataclass

from researchchat.chat.widgets import Picker, PickerOption

MODEL_MODE_ID = "model"
MODEL_MODE_NAME = "Model"
EFFORT_MODE_ID = "effort"
EFFORT_MODE_NAME = "Effort"


@dataclass(frozen=True)
class Picks:
    """What one chat has picked in the chat box pickers."""

    model: str
    effort: str


@dataclass(frozen=True)
class PickerChoices:
    """Everything the pickers may offer: model id -> label and effort level -> label."""

    models: dict[str, str]
    levels: dict[str, str]


def picker_models(names: dict[str, str], default_model: str) -> dict[str, str]:
    """Model id -> label for the picker: the default first, then A→Z by label.

    The default is offered even when OpenRouter doesn't list it (or can't be reached), so the chat
    always has the model config.toml or .env names.
    """
    others = sorted(((label, model_id) for model_id, label in names.items() if model_id != default_model))
    return {default_model: names.get(default_model, default_model), **{model_id: label for label, model_id in others}}


def build_modes(choices: PickerChoices, picks: Picks, can_reason: bool) -> list[Picker]:
    """The pickers to show, each starting at this chat's pick: Model always, Effort only when the model reasons."""
    model_mode = build_picker(MODEL_MODE_ID, MODEL_MODE_NAME, choices.models, picks.model)
    if not can_reason:
        return [model_mode]
    return [model_mode, build_picker(EFFORT_MODE_ID, EFFORT_MODE_NAME, choices.levels, picks.effort)]


def build_picker(mode_id: str, name: str, labels: dict[str, str], picked: str) -> Picker:
    """One picker with an option per entry in config order, the picked one selected."""
    options = tuple(PickerOption(id=value, name=label, selected=value == picked) for value, label in labels.items())
    return Picker(id=mode_id, name=name, options=options)


def chosen_picks(modes: dict[str, str] | None, choices: PickerChoices, fallback: Picks) -> Picks:
    """What a message picked; a value that isn't offered (or is missing) keeps the fallback."""
    sent = modes or {}
    return Picks(
        model=offered_or(sent.get(MODEL_MODE_ID), choices.models, fallback.model),
        effort=offered_or(sent.get(EFFORT_MODE_ID), choices.levels, fallback.effort),
    )


def offered_or(value: str | None, offered: dict[str, str], fallback: str) -> str:
    """`value` when it is one of the offered keys, else `fallback`: the browser can send anything."""
    return value if value in offered else fallback
