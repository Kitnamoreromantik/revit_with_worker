"""
Standalone smoke test for graph/nodes/revit_client.py.

From the repository root:
uv run python revit_code_generator/probe_revit_client.py
uv run python revit_code_generator/probe_revit_client.py --code-file /path/to/script.cs
uv run python revit_code_generator/probe_revit_client.py --code "return \"hello from Revit\";"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap
from pathlib import Path

from graph.nodes.revit_client import RevitExecutor
from utils.mcp_http import get_mcp_config


DEFAULT_CODE = """
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using System.Linq;

UIDocument uidoc = commandData.Application.ActiveUIDocument;
Document doc = uidoc.Document;

int windowCount = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Windows)
    .WhereElementIsNotElementType()
    .Count();

return $"revit_client probe ok. Total windows in model: {windowCount}";
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a C# snippet through RevitExecutor.run_revit_code() without "
            "running the LangGraph pipeline."
        )
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--code",
        help="C# code to execute. If omitted, a read-only window-count probe is used.",
    )
    source_group.add_argument(
        "--code-file",
        type=Path,
        help="Path to a C# file whose contents should be sent to Revit.",
    )
    source_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read C# code from stdin.",
    )
    parser.add_argument(
        "--title",
        default="Standalone Revit MCP client probe",
        help="Log title passed into RevitExecutor.run_revit_code().",
    )
    parser.add_argument(
        "--show-code",
        action="store_true",
        help="Print the exact C# code before sending it.",
    )
    return parser.parse_args()


def read_code(args: argparse.Namespace) -> str:
    if args.code is not None:
        code = args.code
    elif args.code_file is not None:
        code = args.code_file.read_text(encoding="utf-8")
    elif args.stdin:
        code = sys.stdin.read()
    else:
        code = DEFAULT_CODE

    code = textwrap.dedent(code).strip()
    if not code:
        raise ValueError("No C# code provided.")
    return code


async def run_probe(args: argparse.Namespace) -> int:
    code = read_code(args)
    mcp_config = get_mcp_config()

    print(f"Using MCP URL: {mcp_config.url}")
    print(f"Using MCP tool: {mcp_config.tool}")
    if mcp_config.ca_bundle:
        print(f"Using MCP CA bundle: {mcp_config.ca_bundle}")
    if mcp_config.client_cert:
        print(f"Using MCP client cert: {mcp_config.client_cert}")

    if args.show_code:
        print("\nC# code being sent:")
        print("-" * 80)
        print(code)
        print("-" * 80)

    executor = RevitExecutor(name="Standalone Revit MCP client probe")
    error, script_status = await executor.run_revit_code(code, title=args.title)

    print("\nRevitExecutor result:")
    print(f"error: {error or '<none>'}")
    print("script_status:")
    print(script_status or "<empty>")

    return 1 if error or not script_status else 0


def main() -> int:
    args = parse_args()
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main())
