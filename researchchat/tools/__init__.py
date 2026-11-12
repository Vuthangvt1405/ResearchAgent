"""Tools the model can call.

To add a tool: create a module here with DEFINITION, step_title(args) and
async run(args) -> (shown, result), then add it to a list below.
"""

import json

import chainlit as cl

from researchchat.progress import STEP_AVATAR, Progress

from researchchat.tools import (
    dataset_delete,
    dataset_download,
    dataset_list,
    dataset_search,
    notebook_read,
    notebook_run,
    read_page,
    web_search,
)

_MODULES = [web_search, read_page, dataset_search]  # behind the "Web search" switch
# behind the "Notebook" switch; datasets land in the project's files, so they share it (NB-3)
_NOTEBOOK_MODULES = [notebook_read, notebook_run, dataset_download, dataset_list, dataset_delete]

_BY_NAME = {m.DEFINITION["function"]["name"]: m for m in _MODULES + _NOTEBOOK_MODULES}
TOOLS = [m.DEFINITION for m in _MODULES]
NOTEBOOK_TOOLS = [m.DEFINITION for m in _NOTEBOOK_MODULES]


def chosen_tools(settings: dict) -> list[dict]:
    """Tools the model gets, from the settings panel switches."""
    return (TOOLS if settings.get("web_search") else []) + (NOTEBOOK_TOOLS if settings.get("notebook") else [])


async def run_tool_call(call: dict, progress: Progress) -> str:
    """Run one tool call inside a visible chat step; return the model's result."""
    try:
        args = json.loads(call["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}
    module = _BY_NAME.get(call["name"])
    title = module.step_title(args) if module else f"Unknown tool: {call['name']}"
    await progress.step_started(title)

    async with cl.Step(name=title, type="tool", show_input=False, metadata=dict(STEP_AVATAR)) as step:
        try:
            if module is None:
                raise ValueError(f"Bad tool call: {call['name']}({call['arguments']})")
            shown, result = await module.run(args)
            step.output = shown
            return result
        except Exception as e:
            url = args.get("url")
            link = f"\n\n[{url}]({url})" if url else ""
            step.output = f"Failed: {e}{link}"
            return f"Tool failed: {e}"
