"""Tools, Settings, pickers and progress run on the chat ports, with no Chainlit underneath."""

import ast
import asyncio
import json
import re
from pathlib import Path

from researchchat.chat.widgets import Picker, SettingSwitch
from researchchat.modes import PickerChoices, Picks, build_modes
from researchchat.progress import Progress
from researchchat.settings import NO_REASONING_REASON, NO_TOOLS_REASON, build_widgets
from researchchat.tools import run_tool_call, web_search
from researchchat.workspace.kaggle.account import KaggleAccountStatus
from tests.chat.fakes import FakeProgressView

# ---- Business code runs without Chainlit · unit
# Baseline: Given fake ports (progress view, asker, toaster, chat state) · When a tool, the settings
# builder, the pickers or progress run


def known_tool(monkeypatch, run) -> None:
    """Replace web_search's run with `run`, keeping its real name and step title."""
    monkeypatch.setattr(web_search, "run", run)


def test_run_tool_call_shows_one_step_with_the_tool_output(monkeypatch):
    # Given a tool call to a known tool and a FakeProgressView
    # When run_tool_call runs it
    # Then the view got one tool step titled by the tool's step_title, finished with the tool's shown text
    # Demonstrates: a tool step needs no Chainlit
    async def found(args: dict) -> tuple[str, str]:
        return "3 results", "result for the model"

    known_tool(monkeypatch, found)
    view = FakeProgressView()
    call = {"id": "c1", "name": "web_search", "arguments": json.dumps({"query": "hanoi air"})}

    result = asyncio.run(run_tool_call(call, Progress(view)))

    assert result == "result for the model"
    assert [(step.title, step.output) for step in view.tool_steps] == [(web_search.step_title({"query": "hanoi air"}), "3 results")]
    assert view.labels == [web_search.step_title({"query": "hanoi air"})]


def test_build_widgets_returns_our_own_switches():
    # Given a model that reasons and uses tools, and a Kaggle status
    # When build_widgets runs
    # Then it returns SettingSwitch rows with today's ids, labels and greyed-out reasons
    # Demonstrates: Settings content is unchanged, only its type is the app's own
    full = build_widgets({"reasoning", "tools"}, kaggle=KaggleAccountStatus(state="disconnected"))
    bare = build_widgets(set(), kaggle=KaggleAccountStatus(state="connected", username="ana"))

    assert all(isinstance(row, SettingSwitch) for row in full + bare)
    assert [(row.id, row.label, row.disabled) for row in full] == [
        ("show_thinking", "Show thinking", False),
        ("web_search", "Web search", False),
        ("notebook", "Notebook", False),
        ("kaggle_account", "Kaggle account", False),
    ]
    greyed = {row.id: row.description for row in bare if row.disabled}
    assert greyed == {"show_thinking": NO_REASONING_REASON, "web_search": NO_TOOLS_REASON, "notebook": NO_TOOLS_REASON}


def test_build_modes_returns_our_own_pickers():
    # Given picker choices and this chat's picks
    # When build_modes runs for a reasoning model, and again for a model that can't reason
    # Then it returns Picker objects: Model and Effort for the first, Model only for the second
    # Demonstrates: the chat box pickers are unchanged
    choices = PickerChoices(models={"vendor/fast": "Fast", "vendor/smart": "Smart"}, levels={"default": "Model default", "high": "High"})
    picks = Picks(model="vendor/smart", effort="high")

    thinking = build_modes(choices, picks, can_reason=True)
    plain = build_modes(choices, picks, can_reason=False)

    assert all(isinstance(picker, Picker) for picker in thinking + plain)
    assert [picker.id for picker in thinking] == ["model", "effort"]
    assert [picker.id for picker in plain] == ["model"]
    assert [(option.id, option.selected) for option in thinking[0].options] == [("vendor/fast", False), ("vendor/smart", True)]
    assert [(option.id, option.selected) for option in thinking[1].options] == [("default", False), ("high", True)]


def test_nothing_imports_chainlit():
    # Given every module under researchchat/ and tests/, and the requirements files
    # When their imports and requirements are read
    # Then none imports or requires chainlit
    # Demonstrates: Chainlit is fully gone
    importers = [str(path.relative_to(REPO)) for path in python_sources() if imports_chainlit(path)]
    requirers = [path.name for path in REPO.glob("requirements*.txt") if requires_chainlit(path)]

    assert importers == []
    assert requirers == []


REPO = Path(__file__).resolve().parents[2]


def python_sources() -> list[Path]:
    return sorted([*(REPO / "researchchat").rglob("*.py"), *(REPO / "tests").rglob("*.py"), *REPO.glob("*.py")])


def imports_chainlit(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "chainlit" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "chainlit":
            return True
    return False


def requires_chainlit(path: Path) -> bool:
    lines = (line.split("#")[0].strip().lower() for line in path.read_text(encoding="utf-8").splitlines())
    return any(re.match(r"chainlit\b", line) for line in lines)


def test_run_tool_call_reports_failure_in_the_step(monkeypatch):
    # Given a tool that raises, with a url in its arguments
    # When run_tool_call runs it
    # Then the step finishes with "Failed: …" and a link to the url, and the model gets "Tool failed: …"
    # Demonstrates: failures stay visible to the user and to the model
    async def broken(args: dict) -> tuple[str, str]:
        raise ValueError("site down")

    known_tool(monkeypatch, broken)
    view = FakeProgressView()
    call = {"id": "c1", "name": "web_search", "arguments": json.dumps({"query": "q", "url": "https://example.org/a"})}

    result = asyncio.run(run_tool_call(call, Progress(view)))

    assert result == "Tool failed: site down"
    assert view.tool_steps[0].output == "Failed: site down\n\n[https://example.org/a](https://example.org/a)"
