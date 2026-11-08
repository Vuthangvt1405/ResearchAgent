"""Tools the model can call.

To add a tool: create a module here with DEFINITION, step_title(args) and
async run(args) -> (shown, result), then add it to _MODULES below.
"""

import json

import chainlit as cl

from researchchat.progress import Progress

from researchchat.tools import read_page, web_search

_MODULES = [web_search, read_page]

_BY_NAME = {m.DEFINITION["function"]["name"]: m for m in _MODULES}
TOOLS = [m.DEFINITION for m in _MODULES]


async def run_tool_call(call: dict, progress: Progress) -> str:
    """Run one tool call inside a visible chat step; return the model's result."""
    try:
        args = json.loads(call["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}
    module = _BY_NAME.get(call["name"])
    title = module.step_title(args) if module else f"Unknown tool: {call['name']}"
    await progress.step_started(title)

    async with cl.Step(name=title, type="tool", show_input=False) as step:
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
