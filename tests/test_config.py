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
