"""The Model picker says what each model can do."""

import asyncio

from researchchat import llm
from researchchat.chat_start import pickers_for
from researchchat.modes import Picks

THINKS_AND_TOOLS = llm.ModelInfo(id="vendor/smart", name="Smart", params=frozenset({"reasoning", "tools"}))
TOOLS_ONLY = llm.ModelInfo(id="vendor/tools", name="Tools", params=frozenset({"tools"}))
PLAIN = llm.ModelInfo(id="vendor/plain", name="Plain", params=frozenset())

# ---- Model options say what each model can do · unit
# Baseline: Given a catalog with a model that thinks and uses tools, one that only uses tools, and one with neither · When the Model picker is built


def test_model_options_say_what_each_model_can_do(monkeypatch):
    # Changed: nothing
    # Then: details "thinks · tools", "tools", "" in that order; Effort options have no detail
    # Demonstrates: the picker tells models apart
    monkeypatch.setattr(llm, "_catalog", {model.id: model for model in (THINKS_AND_TOOLS, TOOLS_ONLY, PLAIN)})

    model_picker, effort_picker = asyncio.run(pickers_for(Picks(model="vendor/smart", effort="default")))

    details = {option.id: option.detail for option in model_picker.options}
    assert (details["vendor/smart"], details["vendor/tools"], details["vendor/plain"]) == ("thinks · tools", "tools", "")
    assert {option.detail for option in effort_picker.options} == {""}
