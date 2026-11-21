"""The app's tools in a LangChain agent: the agent learns their schemas, and every call it makes runs
through the app's own run_tool_call, so steps, Run / Skip prompts and failures look exactly as before."""

import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool

from researchchat.progress import Progress
from researchchat.tools import run_tool_call


def langchain_tools(definitions: list[dict]) -> list[StructuredTool]:
    """The tools as the model sees them; their calls are run by AppToolCalls, never by these objects."""
    return [schema_only_tool(definition["function"]) for definition in definitions]


def schema_only_tool(function: dict) -> StructuredTool:
    async def run_elsewhere(**_arguments: object) -> str:
        raise RuntimeError("tool calls run through AppToolCalls")

    return StructuredTool.from_function(
        coroutine=run_elsewhere, name=function["name"], description=function["description"], args_schema=function["parameters"]
    )


class AppToolCalls(AgentMiddleware):
    """Runs each tool call the model makes through the app, including unknown tool names."""

    def __init__(self, progress: Progress) -> None:
        super().__init__()
        self.progress = progress

    async def awrap_tool_call(self, request, handler) -> ToolMessage:
        call = request.tool_call
        app_call = {"id": call["id"], "name": call["name"], "arguments": json.dumps(call["args"])}
        result = await run_tool_call(app_call, self.progress)
        return ToolMessage(content=result, tool_call_id=call["id"], name=call["name"])
