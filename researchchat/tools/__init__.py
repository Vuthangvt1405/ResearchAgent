"""Tools the model can call.

To add a tool: create a module here with DEFINITION, step_title(args) and
async run(args) -> (shown, result), then add it to a list below.
"""

import json

from researchchat.progress import Progress
from researchchat.tools import (
    dataset_delete,
    dataset_describe,
    dataset_download,
    dataset_list,
    dataset_search,
    notebook_read,
    notebook_run,
    read_page,
    web_search,
)

_MODULES = [web_search, read_page, dataset_search]  # behind the "Web search" switch
# behind the "Notebook" switch; datasets land in the project's files, so they share it
_NOTEBOOK_MODULES = [notebook_read, notebook_run, dataset_download, dataset_list, dataset_delete, dataset_describe]

_BY_NAME = {m.DEFINITION["function"]["name"]: m for m in _MODULES + _NOTEBOOK_MODULES}
TOOLS = [m.DEFINITION for m in _MODULES]
NOTEBOOK_TOOLS = [m.DEFINITION for m in _NOTEBOOK_MODULES]


def chosen_tools(settings: dict) -> list[dict]:
    """Tools the model gets, from the settings panel switches."""
    return (TOOLS if settings.get("web_search") else []) + (NOTEBOOK_TOOLS if settings.get("notebook") else [])


async def run_tool_call(call: dict, progress: Progress) -> str:
    """Run one tool call as a visible step in the reply's work group; return the model's result."""
    try:
        args = json.loads(call["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}
    module = _BY_NAME.get(call["name"])
    title = module.step_title(args) if module else f"Unknown tool: {call['name']}"
    step = await progress.start_tool_step(title)
    try:
        if module is None:
            raise ValueError(f"Bad tool call: {call['name']}({call['arguments']})")
        shown, result = await module.run(args)
    except Exception as e:
        await step.finish(failure_text(e, args.get("url")))
        return f"Tool failed: {e}"
    await step.finish(shown)
    return result


def failure_text(error: Exception, url: object) -> str:
    """What a failed step shows: the reason, and the page it was reading when there is one."""
    link = f"\n\n[{url}]({url})" if url else ""
    return f"Failed: {error}{link}"
