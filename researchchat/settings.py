"""The chat settings panel (gear icon) and what its values mean for requests."""

from chainlit.input_widget import InputWidget, Select, Switch

from researchchat.config import EFFORT_DEFAULT, EFFORT_LEVELS, SEARCH_ENABLED


def build_widgets(model_params: set[str]) -> list[InputWidget]:
    """Settings to show, based on what the model supports."""
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
