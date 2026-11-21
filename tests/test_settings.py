from sillytherin.settings import (
    NO_REASONING_REASON,
    NO_TOOLS_REASON,
    build_widgets,
    keep_chat_choices,
    reasoning_body,
    usable_settings,
)
from sillytherin.workspace.kaggle.account import KaggleAccountStatus

NOT_CONNECTED = KaggleAccountStatus(state="disconnected")
FULL_MODEL = {"reasoning", "tools"}


def ids(widgets):
    return [w.id for w in widgets]


def by_id(widgets):
    return {w.id: w for w in widgets}


def test_settings_have_no_effort_row_and_run_answers_tools_accounts():
    # Given a model that reasons and uses tools, Then Settings shows Show thinking, Web search, Notebook, Kaggle in that order
    widgets = build_widgets(FULL_MODEL, kaggle=NOT_CONNECTED)
    assert ids(widgets) == ["show_thinking", "web_search", "notebook", "kaggle_account"]
    assert not any(w.disabled for w in widgets)


def test_rows_stay_greyed_with_a_reason_when_model_lacks_the_feature():
    # Given a model without tools or reasoning, Then those rows are shown off and disabled with why
    rows = by_id(build_widgets(set(), kaggle=NOT_CONNECTED))
    assert (rows["show_thinking"].disabled, rows["show_thinking"].initial) == (True, False)
    assert rows["show_thinking"].description == NO_REASONING_REASON
    for tool_row in ("web_search", "notebook"):
        assert (rows[tool_row].disabled, rows[tool_row].initial) == (True, False)
        assert rows[tool_row].description == NO_TOOLS_REASON
    assert not rows["kaggle_account"].disabled


def test_resent_settings_keep_chat_choices():
    # a refresh after a Kaggle change must not reset what this chat picked, but the switch shows the account
    widgets = build_widgets(FULL_MODEL, kaggle=KaggleAccountStatus("connected", username="ana"))
    kept = keep_chat_choices(widgets, {"web_search": False, "notebook": False, "kaggle_account": False})
    assert [(w.id, w.initial) for w in kept][1:] == [("web_search", False), ("notebook", False), ("kaggle_account", True)]


def test_greyed_rows_ignore_earlier_choices():
    # switching to a model without tools must not leave a greyed switch showing on
    widgets = build_widgets({"reasoning"}, kaggle=NOT_CONNECTED)
    kept = by_id(keep_chat_choices(widgets, {"web_search": True, "notebook": True}))
    assert (kept["web_search"].initial, kept["notebook"].initial) == (False, False)


def test_no_tools_reach_a_model_without_tools():
    chosen = {"web_search": True, "notebook": True, "show_thinking": True}
    assert usable_settings(chosen, {"reasoning"}) == {"web_search": False, "notebook": False, "show_thinking": True}
    assert usable_settings(chosen, FULL_MODEL) == chosen


def test_each_switch_adds_its_own_tools():
    from sillytherin.tools import chosen_tools

    names = lambda s: [t["function"]["name"] for t in chosen_tools(s)]
    assert names({}) == []
    assert names({"web_search": True}) == ["web_search", "read_page", "dataset_search"]
    notebook = ["notebook_read", "notebook_run", "dataset_download", "dataset_list", "dataset_delete", "dataset_describe"]
    assert names({"notebook": True}) == notebook
    assert names({"web_search": True, "notebook": True}) == ["web_search", "read_page", "dataset_search"] + notebook


def test_no_reasoning_field_when_model_cannot_reason_whatever_effort_says():
    # Given a model without reasoning and effort "high", Then the request carries no reasoning field
    assert reasoning_body(effort="high", show_thinking=False, can_reason=False) == {}
    assert reasoning_body(effort="off", show_thinking=True, can_reason=False) == {}


def test_effort_and_show_thinking_build_the_same_bodies_as_before():
    # Given each effort level with Show thinking on and off, Then the reasoning field matches today's
    assert reasoning_body(effort="default", show_thinking=True, can_reason=True) == {}
    assert reasoning_body(effort="default", show_thinking=False, can_reason=True) == {"reasoning": {"exclude": True}}
    assert reasoning_body(effort="off", show_thinking=False, can_reason=True) == {"reasoning": {"enabled": False}}
    assert reasoning_body(effort="high", show_thinking=True, can_reason=True) == {"reasoning": {"effort": "high"}}
    assert reasoning_body(effort="high", show_thinking=False, can_reason=True) == {
        "reasoning": {"effort": "high", "exclude": True}
    }
