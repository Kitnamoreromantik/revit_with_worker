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
import json
import os
import socket
import sys
import textwrap
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from graph.nodes.revit_client import RevitExecutor, mcp_result_to_text
from utils.mcp_http import (
    DEFAULT_MCP_CONFIG_PATH,
    get_mcp_config,
    get_ssl_verify_config,
)


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
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip TCP, HTTP initialize, and tool-list preflight checks.",
    )
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        help="Run diagnostics only; do not execute the C# code.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=("executor", "direct-sdk"),
        default="executor",
        help=(
            "executor calls RevitExecutor.run_revit_code(); direct-sdk calls the "
            "same MCP tool directly and prints lower-level MCP exceptions."
        ),
    )
    parser.add_argument(
        "--diagnose-call-on-error",
        action="store_true",
        help=(
            "If RevitExecutor fails, re-send the same code through a direct MCP SDK "
            "call to expose lower-level exceptions. This may execute the code twice."
        ),
    )
    parser.add_argument(
        "--show-tools-schema",
        action="store_true",
        help="Print full MCP input schemas during the tool-list preflight.",
    )
    parser.add_argument(
        "--tcp-timeout",
        type=float,
        default=3.0,
        help="TCP reachability timeout in seconds.",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=20.0,
        help="HTTP connect timeout in seconds.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=60.0,
        help="HTTP read timeout in seconds.",
    )
    parser.add_argument(
        "--tracebacks",
        action="store_true",
        help="Print tracebacks for flattened exception-group members.",
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


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def current_config_path() -> Path:
    config_path = Path(
        os.getenv("REVIT_MCP_CONFIG", DEFAULT_MCP_CONFIG_PATH)
    ).expanduser()
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    return config_path


def describe_path(label: str, value: str) -> None:
    if not value:
        print(f"{label}: <not configured>")
        return

    path = Path(value)
    if not path.exists():
        print(f"{label}: {path} (missing)")
        return

    stat = path.stat()
    print(f"{label}: {path} ({stat.st_size} bytes, mode {stat.st_mode & 0o777:o})")


def print_config_summary(mcp_config) -> None:
    print_section("MCP configuration")
    print(f"Config file: {current_config_path()}")
    print(f"URL: {mcp_config.url}")
    print(f"Tool: {mcp_config.tool}")
    print(f"Token configured: {'yes' if mcp_config.token else 'no'}")
    print(f"Insecure SSL: {mcp_config.insecure_ssl}")
    describe_path("CA bundle", mcp_config.ca_bundle)
    describe_path("Client cert", mcp_config.client_cert)
    describe_path("Client key", mcp_config.client_key)


def flatten_exception_group(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        result = []
        for inner in exc.exceptions:
            result.extend(flatten_exception_group(inner))
        return result
    return [exc]


def explain_errors(errors: list[BaseException]) -> None:
    if any(
        isinstance(e, (socket.timeout, TimeoutError, httpx.ConnectTimeout))
        for e in errors
    ):
        print(
            "\nLikely meaning: TCP connection timed out. The host/port is unreachable, "
            "blocked by routing/firewall/VPN, or the server is not listening."
        )
    elif any(isinstance(e, httpx.ConnectError) for e in errors):
        joined = "\n".join(str(e) for e in errors).lower()
        if "nodename nor servname" in joined or "name or service not known" in joined:
            print(
                "\nLikely meaning: DNS cannot resolve the MCP hostname from this machine."
            )
        else:
            print(
                "\nLikely meaning: the client could not open a connection. Check host, "
                "port, VPN/routing, server availability, and TLS client certificate."
            )
    elif any(isinstance(e, httpx.ReadTimeout) for e in errors):
        print(
            "\nLikely meaning: the connection opened, but the MCP server or downstream "
            "Revit worker did not respond before the read timeout."
        )
    elif any(isinstance(e, httpx.HTTPStatusError) for e in errors):
        print(
            "\nLikely meaning: the MCP endpoint responded with a non-2xx HTTP status."
        )
    elif any(isinstance(e, httpx.RemoteProtocolError) for e in errors):
        print(
            "\nLikely meaning: the server response did not match the expected HTTP/MCP "
            "streamable-http protocol."
        )


def print_exception_summary(exc: BaseException, *, tracebacks: bool = False) -> None:
    errors = flatten_exception_group(exc)

    print("\nFailure details:")
    for i, err in enumerate(errors, start=1):
        print(f"\n[{i}] {type(err).__name__}: {err}")
        print(f"repr: {err!r}")

        request = getattr(err, "request", None)
        if request is not None:
            print(f"Request: {request.method} {request.url}")

        response = getattr(err, "response", None)
        if response is not None:
            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type', '')}")
            session_id = response.headers.get("mcp-session-id")
            if session_id:
                print(f"MCP session id: {session_id}")
            try:
                body = response.text.strip()
            except httpx.ResponseNotRead:
                body = ""
                print(
                    "Response body was not read because the SDK uses a streaming response."
                )
            if body:
                print("Response body:")
                print(body[:4000])

        if tracebacks:
            import traceback

            traceback.print_exception(type(err), err, err.__traceback__)

    explain_errors(errors)


def parse_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError(f"Cannot parse hostname from URL: {url}")

    if parsed.port:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80

    return parsed.hostname, port


def http_timeout(args: argparse.Namespace) -> httpx.Timeout:
    return httpx.Timeout(
        connect=args.connect_timeout,
        read=args.read_timeout,
        write=30.0,
        pool=20.0,
    )


def auth_headers(mcp_config) -> dict[str, str]:
    headers = {}
    if mcp_config.token:
        headers["Authorization"] = f"Bearer {mcp_config.token}"
    return headers


async def run_diagnostic_step(
    name: str,
    coro,
    *,
    tracebacks: bool,
) -> bool:
    print_section(name)
    start = time.monotonic()
    try:
        await coro
    except (
        BaseExceptionGroup,
        socket.timeout,
        TimeoutError,
        ConnectionRefusedError,
        OSError,
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.HTTPError,
    ) as exc:
        print_exception_summary(exc, tracebacks=tracebacks)
        print(f"\nStep failed after {time.monotonic() - start:.2f}s")
        return False
    except Exception as exc:
        print_exception_summary(exc, tracebacks=tracebacks)
        print(f"\nStep failed after {time.monotonic() - start:.2f}s")
        return False

    print(f"\nStep completed in {time.monotonic() - start:.2f}s")
    return True


async def check_tcp_reachable(url: str, timeout_seconds: float) -> None:
    host, port = parse_host_port(url)
    print(f"Opening TCP socket to {host}:{port} with timeout {timeout_seconds:.1f}s")

    def connect() -> None:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass

    await asyncio.to_thread(connect)
    print(f"TCP reachable: {host}:{port}")


async def probe_initialize_response(mcp_config, args: argparse.Namespace) -> None:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **auth_headers(mcp_config),
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "probe-revit-client",
                "version": "0.1.0",
            },
        },
    }

    async with httpx.AsyncClient(
        headers=headers,
        timeout=http_timeout(args),
        follow_redirects=True,
        http2=True,
        verify=get_ssl_verify_config(mcp_config),
    ) as http_client:
        response = await http_client.post(mcp_config.url, json=payload)

    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type', '')}")
    session_id = response.headers.get("mcp-session-id")
    if session_id:
        print(f"MCP session id: {session_id}")

    body = response.text.strip()
    if body:
        print("Response body:")
        print(body[:4000])

    response.raise_for_status()


async def probe_list_tools(mcp_config, args: argparse.Namespace) -> None:
    async with httpx.AsyncClient(
        headers=auth_headers(mcp_config),
        timeout=http_timeout(args),
        follow_redirects=True,
        http2=True,
        verify=get_ssl_verify_config(mcp_config),
    ) as http_client:
        async with streamable_http_client(mcp_config.url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                print("Initializing MCP SDK session...")
                await session.initialize()
                print("Listing MCP tools...")
                tools_response = await session.list_tools()

    tools = list(tools_response.tools or [])
    if not tools:
        raise RuntimeError("MCP server is reachable, but it returned no tools.")

    found_configured_tool = False
    for tool in tools:
        print(f"\nTool: {tool.name}")
        print(f"Description: {tool.description}")
        if tool.name == mcp_config.tool:
            found_configured_tool = True
        if args.show_tools_schema:
            schema = getattr(tool, "inputSchema", None)
            if schema is None:
                schema = getattr(tool, "input_schema", None)
            print("Input schema:")
            print(json.dumps(schema, indent=2, ensure_ascii=False))

    if not found_configured_tool:
        tool_names = ", ".join(tool.name for tool in tools)
        raise RuntimeError(
            f"Configured tool {mcp_config.tool!r} was not returned by list_tools(). "
            f"Available tools: {tool_names}"
        )


async def execute_with_revit_executor(
    code: str, args: argparse.Namespace
) -> tuple[bool, str | None]:
    print_section("Execute through RevitExecutor")
    start = time.monotonic()
    executor = RevitExecutor(name="Standalone Revit MCP client probe")
    error, script_status = await executor.run_revit_code(code, title=args.title)

    print("\nRevitExecutor result:")
    print(f"error: {error or '<none>'}")
    print("script_status:")
    print(script_status or "<empty>")
    print(f"\nStep completed in {time.monotonic() - start:.2f}s")

    return not error and bool(script_status), error


async def execute_with_direct_sdk(
    code: str, mcp_config, args: argparse.Namespace
) -> bool:
    print_section("Execute through direct MCP SDK diagnostic call")
    print(
        "This bypasses RevitExecutor's broad exception handler, but uses the same "
        "MCP URL, TLS settings, tool name, and code payload."
    )
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(
            headers=auth_headers(mcp_config),
            timeout=http_timeout(args),
            follow_redirects=True,
            http2=True,
            verify=get_ssl_verify_config(mcp_config),
        ) as http_client:
            async with streamable_http_client(
                mcp_config.url, http_client=http_client
            ) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    print("Initializing MCP SDK session...")
                    await session.initialize()
                    print(f"Calling tool {mcp_config.tool!r} with code payload...")
                    result = await session.call_tool(mcp_config.tool, {"code": code})

        print("\nRaw MCP result object:")
        print(result)
        print("\nRendered MCP result text:")
        print(mcp_result_to_text(result))
        print(f"\nStep completed in {time.monotonic() - start:.2f}s")
        return True

    except (
        BaseExceptionGroup,
        socket.timeout,
        TimeoutError,
        ConnectionRefusedError,
        OSError,
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.HTTPError,
    ) as exc:
        print_exception_summary(exc, tracebacks=args.tracebacks)
        print(f"\nStep failed after {time.monotonic() - start:.2f}s")
        return False
    except Exception as exc:
        print_exception_summary(exc, tracebacks=args.tracebacks)
        print(f"\nStep failed after {time.monotonic() - start:.2f}s")
        return False


async def run_preflight(mcp_config, args: argparse.Namespace) -> bool:
    tcp_ok = await run_diagnostic_step(
        "Preflight 1/3: TCP reachability",
        check_tcp_reachable(mcp_config.url, args.tcp_timeout),
        tracebacks=args.tracebacks,
    )
    if not tcp_ok:
        print("\nStopping preflight early because raw TCP connectivity failed.")
        return False

    initialize_ok = await run_diagnostic_step(
        "Preflight 2/3: raw HTTP initialize",
        probe_initialize_response(mcp_config, args),
        tracebacks=args.tracebacks,
    )
    if not initialize_ok:
        print("\nStopping preflight early because MCP initialize failed.")
        return False

    return await run_diagnostic_step(
        "Preflight 3/3: MCP SDK initialize and list_tools",
        probe_list_tools(mcp_config, args),
        tracebacks=args.tracebacks,
    )


async def run_probe(args: argparse.Namespace) -> int:
    code = read_code(args)
    mcp_config = get_mcp_config()

    print_config_summary(mcp_config)
    print(
        f"\nCode payload: {len(code.splitlines())} lines, {len(code.encode('utf-8'))} bytes"
    )

    if args.show_code:
        print("\nC# code being sent:")
        print("-" * 80)
        print(code)
        print("-" * 80)

    preflight_ok = True
    if not args.skip_preflight:
        preflight_ok = await run_preflight(mcp_config, args)

    if args.skip_execution:
        return 0 if preflight_ok else 1

    if not preflight_ok:
        print(
            "\nSkipping code execution because preflight failed. Use --skip-preflight to force execution."
        )
        return 1

    if args.execution_mode == "direct-sdk":
        return 0 if await execute_with_direct_sdk(code, mcp_config, args) else 1

    executor_ok, executor_error = await execute_with_revit_executor(code, args)
    if executor_ok:
        return 0

    if args.diagnose_call_on_error:
        print(
            "\nRe-sending the same code through the direct MCP SDK because "
            "--diagnose-call-on-error was set."
        )
        direct_ok = await execute_with_direct_sdk(code, mcp_config, args)
        return 0 if direct_ok else 1

    if executor_error:
        print(
            "\nFor lower-level MCP call details, rerun with "
            "--execution-mode direct-sdk. If you want that only after a "
            "RevitExecutor failure, use --diagnose-call-on-error; it may execute "
            "the code twice."
        )
    return 1


def main() -> int:
    args = parse_args()
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main())
