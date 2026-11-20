"""The Model and Effort pickers in the chat box."""

from researchchat.modes import (
    EFFORT_MODE_ID,
    MODEL_MODE_ID,
    PickerChoices,
    Picks,
    build_modes,
    chosen_picks,
    picker_models,
)

CHOICES = PickerChoices(
    models={"vendor/fast": "Fast", "vendor/smart": "Smart"},
    levels={"default": "Model default", "off": "Off", "high": "High"},
)
DEFAULTS = Picks(model="vendor/fast", effort="default")


def options(mode):
    return [(o.id, o.name, o.selected) for o in mode.options]


def test_model_picker_lists_every_configured_model_with_default_marked():
    # Given two configured models, When the pickers are built, Then both show in config order and the default is marked
    model_mode = build_modes(CHOICES, DEFAULTS, can_reason=True)[0]
    assert (model_mode.id, model_mode.name) == (MODEL_MODE_ID, "Model")
    assert options(model_mode) == [("vendor/fast", "Fast", True), ("vendor/smart", "Smart", False)]


def test_effort_picker_lists_levels_in_config_order_with_default_marked():
    # Given the configured effort levels, When the picker is built, Then they show in order and the default is marked
    effort_mode = build_modes(CHOICES, DEFAULTS, can_reason=True)[1]
    assert (effort_mode.id, effort_mode.name) == (EFFORT_MODE_ID, "Effort")
    assert options(effort_mode) == [("default", "Model default", True), ("off", "Off", False), ("high", "High", False)]


def test_no_effort_picker_when_model_cannot_reason():
    # Given a model without reasoning support, When the pickers are built, Then only the Model picker is sent
    assert [m.id for m in build_modes(CHOICES, DEFAULTS, can_reason=False)] == [MODEL_MODE_ID]


def test_offered_model_is_used():
    # Given a message that picked a configured model, Then that model is requested
    picks = chosen_picks({"model": "vendor/smart", "effort": "high"}, CHOICES, DEFAULTS)
    assert picks == Picks(model="vendor/smart", effort="high")


def test_missing_modes_fall_back_to_defaults():
    # Given a message with no picker values, Then the default model and effort are used
    assert chosen_picks(None, CHOICES, DEFAULTS) == DEFAULTS
    assert chosen_picks({}, CHOICES, DEFAULTS) == DEFAULTS


def test_unknown_model_id_falls_back_to_default():
    # Given a browser that sends a model id nobody configured, Then the default model is requested instead
    assert chosen_picks({"model": "vendor/expensive"}, CHOICES, DEFAULTS).model == "vendor/fast"


def test_unknown_effort_falls_back_to_default():
    # Given an effort level that isn't configured, Then the default effort is used
    assert chosen_picks({"effort": "xhigh"}, CHOICES, DEFAULTS).effort == "default"


def test_default_model_is_offered_first_even_when_openrouter_does_not_list_it():
    # Given OPENROUTER_MODEL names a model OpenRouter doesn't list, Then the picker still offers it, first
    assert list(picker_models({"vendor/smart": "Smart"}, "vendor/fast")) == ["vendor/fast", "vendor/smart"]


def test_picker_lists_the_default_first_then_a_to_z_by_name():
    names = {"z/zeta": "Zeta", "a/alpha": "Alpha", "vendor/fast": "Fast"}
    assert picker_models(names, "vendor/fast") == {"vendor/fast": "Fast", "a/alpha": "Alpha", "z/zeta": "Zeta"}


def test_unreachable_openrouter_leaves_only_the_configured_model():
    assert picker_models({}, "vendor/fast") == {"vendor/fast": "vendor/fast"}


def test_resumed_chat_keeps_its_model_and_effort():
    # Given a chat that picked a model and effort, When the pickers are sent again, Then they start at those picks
    picks = Picks(model="vendor/smart", effort="high")
    model_mode, effort_mode = build_modes(CHOICES, picks, can_reason=True)
    assert [o.id for o in model_mode.options if o.selected] == ["vendor/smart"]
    assert [o.id for o in effort_mode.options if o.selected] == ["high"]
    # a message from a model without the Effort picker keeps the earlier effort
    assert chosen_picks({"model": "vendor/fast"}, CHOICES, picks).effort == "high"
