import textwrap
import json
import os
from typing import Any

import httpx
from rich import print
from rich.panel import Panel

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from graph.states.graph_state import GraphState
from graph.nodes.node_lib.base_node import BaseNode
from utils.logger import logger


MCP_URL = os.getenv("REVIT_MCP_URL")
MCP_TOOL_NAME = os.getenv("REVIT_MCP_TOOL")
MCP_TOKEN = os.getenv("REVIT_MCP_TOKEN", "")


def mcp_result_to_text(result: Any) -> str:
    """
    Converts MCP CallToolResult into a readable string for GraphState.script_result.
    Handles both text content and structuredContent if the server returns it.
    """

    text_parts = []

    for item in getattr(result, "content", []) or []:
        item_type = getattr(item, "type", None)

        if item_type == "text":
            text_parts.append(getattr(item, "text", ""))
        else:
            text_parts.append(str(item))

    # MCP Python objects may expose structured content with either naming style
    # depending on SDK/model layer.
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)

    if structured is not None:
        try:
            structured_text = json.dumps(structured, indent=2, ensure_ascii=False)
        except Exception:
            structured_text = str(structured)

        if text_parts:
            text_parts.append("\nStructured content:\n" + structured_text)
        else:
            text_parts.append(structured_text)

    is_error = getattr(result, "isError", None)
    if is_error is None:
        is_error = getattr(result, "is_error", False)

    output = "\n".join(part for part in text_parts if part is not None).strip()

    if not output:
        output = str(result)

    if is_error:
        return f"MCP tool returned error:\n{output}"

    return output


class RevitExecutor(BaseNode):
    """
    LangGraph node that executes C# Revit code through an MCP server.
    Old version: direct requests.post(...)
    New version: MCP ClientSession + call_tool(...)
    """

    async def run_revit_code(self, code: str, title: str | None = None):
        script_status = None
        error = None

        code = textwrap.dedent(code).strip()
        logger.info(f"{title or 'Revit MCP client running'}")

        headers = {}
        if MCP_TOKEN:
            headers["Authorization"] = f"Bearer {MCP_TOKEN}"

        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=60.0,
                follow_redirects=True,
            ) as http_client:
                async with streamable_http_client(
                    MCP_URL,
                    http_client=http_client,
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()

                        result = await session.call_tool(
                            MCP_TOOL_NAME,
                            {
                                "code": code
                            },
                        )

                        script_status = mcp_result_to_text(result)
                        logger.info(script_status)

        except Exception as e:
            error = f"MCP connection/tool error: {e}"
            logger.error(error)

        return error, script_status

    async def pre_hook(self, _: GraphState) -> None:
        self.log_banner()
        print("\n----------------------------")
        print("Revit MCP client running\n")

    async def core_logic(self, node_input: GraphState) -> GraphState:
        if not node_input.script:
            return GraphState(
                user_messages=node_input.user_messages,
                script="None",
                script_explanation=node_input.script_explanation,
                script_result="No script found from the Generator agent!",
                num_of_generation_attempts=node_input.num_of_generation_attempts,
                errors="node_input.script is empty!",
            )

        try:
            err_msg, script_res = await self.run_revit_code(node_input.script)

        except Exception as err:
            err_msg = str(err) or "Unknown exception from the Revit MCP client!"
            logger.error(err_msg)
            script_res = f"Revit MCP client has thrown the exception: {err_msg}!"

        if err_msg:
            logger.error(err_msg)
            script_res = f"Revit MCP client has thrown the exception: {err_msg}!"

        return GraphState(
            user_messages=node_input.user_messages,
            script=node_input.script,
            script_explanation=node_input.script_explanation,
            script_result=script_res,
            num_of_generation_attempts=node_input.num_of_generation_attempts,
            errors=err_msg,
        )

    async def test_logic(self, node_input: GraphState) -> GraphState:
        return GraphState(
            user_messages=node_input.user_messages,
            script=node_input.script,
            script_explanation=node_input.script_explanation,
            script_result="Status: 200 Response: Total windows in model: 7",
            num_of_generation_attempts=node_input.num_of_generation_attempts,
        )

    async def post_hook(self, node_output: GraphState) -> None:
        try:
            formatted = json.dumps(node_output.script_result, indent=4, ensure_ascii=False)
        except Exception:
            formatted = str(node_output.script_result)

        logger.info(f"\n{formatted}")

        MAX_LINES = 50
        lines = formatted.splitlines()
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + ["...", "[Output truncated]"]

        display_text = "\n".join(lines)

        print(
            Panel(
                display_text,
                title=f"{self.name}",
                title_align="left",
                expand=False,
            )
        )

    def chainlit_output_render_step(self, node_output: dict) -> str:
        script_status = node_output.get("script_result")
        return f"**Script outcome:**\n{script_status}" if script_status else "Empty script status!"
