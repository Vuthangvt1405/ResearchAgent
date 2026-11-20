from researchchat.settings import build_widgets, keep_chat_choices, reasoning_body
from researchchat.workspace.kaggle.account import KaggleAccountStatus

NOT_CONNECTED = KaggleAccountStatus(state="disconnected")


def ids(widgets):
    return [w.id for w in widgets]


def test_thinking_settings_need_reasoning_support():
    assert ids(build_widgets({"reasoning"}, kaggle=NOT_CONNECTED)) == ["thinking_effort", "show_thinking", "kaggle_account"]


def test_tool_switches_need_tool_support():
    assert ids(build_widgets({"tools"}, kaggle=NOT_CONNECTED)) == ["web_search", "notebook", "kaggle_account"]


def test_resent_settings_keep_chat_choices():
    # a refresh after a Kaggle change must not reset what this chat picked, but the switch shows the account
    widgets = build_widgets({"tools"}, kaggle=KaggleAccountStatus("connected", username="ana"))
    kept = keep_chat_choices(widgets, {"web_search": False, "notebook": False, "kaggle_account": False})
    assert [(w.id, w.initial) for w in kept] == [("web_search", False), ("notebook", False), ("kaggle_account", True)]


def test_each_switch_adds_its_own_tools():
    from researchchat.tools import chosen_tools

    names = lambda s: [t["function"]["name"] for t in chosen_tools(s)]
    assert names({}) == []
    assert names({"web_search": True}) == ["web_search", "read_page", "dataset_search"]
    notebook = ["notebook_read", "notebook_run", "dataset_download", "dataset_list", "dataset_delete", "dataset_describe"]
    assert names({"notebook": True}) == notebook
    assert names({"web_search": True, "notebook": True}) == ["web_search", "read_page", "dataset_search"] + notebook


def test_no_reasoning_field_without_thinking_settings():
    assert reasoning_body({}) == {}
    assert reasoning_body({"web_search": True}) == {}


def test_model_default_sends_nothing():
    assert reasoning_body({"thinking_effort": "default", "show_thinking": True}) == {}


def test_off_disables_reasoning():
    assert reasoning_body({"thinking_effort": "off", "show_thinking": True}) == {
        "reasoning": {"enabled": False}
    }


def test_effort_and_hidden_thinking():
    assert reasoning_body({"thinking_effort": "high", "show_thinking": False}) == {
        "reasoning": {"effort": "high", "exclude": True}
    }
