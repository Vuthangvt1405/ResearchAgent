"""Which Python versions the app starts on, now that nothing blocks 3.14."""

from researchchat.config import setup_problems

A_KEY = "sk-or-test-key"

# ---- Python versions · unit
# Baseline: Given the startup checks · When the app checks the Python version


def test_python_3_14_is_accepted():
    # Changed: version 3.14
    # Then: no setup problem
    # Demonstrates: 3.14 works
    assert setup_problems(version=(3, 14), api_key=A_KEY) == []


def test_python_3_11_is_still_accepted():
    # Changed: version 3.11
    # Then: no setup problem
    # Demonstrates: the oldest supported version still works
    assert setup_problems(version=(3, 11), api_key=A_KEY) == []


def test_python_3_15_is_refused():
    # Changed: version 3.15
    # Then: the step "isn't supported; use 3.11-3.14"
    # Demonstrates: untested versions are refused with steps to fix
    [problem] = setup_problems(version=(3, 15), api_key=A_KEY)
    assert "Python 3.15 isn't supported; use 3.11-3.14." in problem
