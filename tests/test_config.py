import pytest

from researchchat.config import EFFORT_DEFAULT, EFFORT_LEVELS, check_levels


def test_config_toml_loads_with_valid_levels():
    assert EFFORT_LEVELS
    assert EFFORT_DEFAULT in EFFORT_LEVELS


def test_custom_labels_are_allowed():
    check_levels({"off": "No thinking", "low": "Quick", "high": "Deep"})


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError, match="unknown level"):
        check_levels({"low": "Low", "turbo": "Turbo"})


def test_empty_levels_are_rejected():
    with pytest.raises(ValueError, match="empty"):
        check_levels({})


def test_setup_ok_on_supported_python_with_key():
    from researchchat.config import setup_problems

    assert setup_problems((3, 11), "sk-or-123") == []
    assert setup_problems((3, 13), "sk-or-123") == []


def test_setup_rejects_unsupported_python():
    from researchchat.config import setup_problems

    for version in ((3, 10), (3, 14)):
        [problem] = setup_problems(version, "sk-or-123")
        assert f"Python {version[0]}.{version[1]} isn't supported" in problem and "scripts/setup.sh" in problem


def test_setup_needs_a_real_api_key():
    from researchchat.config import setup_problems

    for key in (None, "", "  ", "your-key-here"):
        [problem] = setup_problems((3, 11), key)
        assert "OPENROUTER_API_KEY" in problem and ".env" in problem
