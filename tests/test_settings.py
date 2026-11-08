from researchchat.settings import build_widgets, reasoning_body


def ids(widgets):
    return [w.id for w in widgets]


def test_no_panel_for_plain_model():
    assert build_widgets(set()) == []


def test_thinking_settings_need_reasoning_support():
    assert ids(build_widgets({"reasoning"})) == ["thinking_effort", "show_thinking"]


def test_web_search_switch_needs_tool_support():
    assert ids(build_widgets({"tools"})) == ["web_search"]


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
