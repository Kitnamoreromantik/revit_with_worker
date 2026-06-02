"""
uv run python revit_code_generator/check_revit_mcp_tools.py
"""

import asyncio
import json
import socket
from typing import Iterable
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from utils.mcp_http import get_client_cert_config, get_mcp_config, get_ssl_verify_config


MCP_CONFIG = get_mcp_config()


def flatten_exception_group(exc: BaseException) -> list[BaseException]:
    """
    Turns ExceptionGroup/BaseExceptionGroup into a flat list of real inner exceptions.
    Useful because anyio TaskGroup often wraps network errors.
    """
    if isinstance(exc, BaseExceptionGroup):
        result = []
        for inner in exc.exceptions:
            result.extend(flatten_exception_group(inner))
        return result

    return [exc]


def print_exception_summary(exc: BaseException) -> None:
    errors = flatten_exception_group(exc)

    print("\nConnection failed.")
    print(f"MCP_URL: {MCP_CONFIG.url}")

    for i, err in enumerate(errors, start=1):
        print(f"\n[{i}] {type(err).__name__}: {err}")

    if any(isinstance(e, httpx.ConnectTimeout) for e in errors):
        print(
            "\nMeaning: TCP connection timed out. "
            "The host/port is unreachable, blocked, or not listening."
        )

    elif any(isinstance(e, httpx.ConnectError) for e in errors):
        print(
            "\nMeaning: connection failed immediately. "
            "Usually wrong host, wrong port, server not running, or DNS failure."
        )

    elif any(isinstance(e, httpx.ReadTimeout) for e in errors):
        print(
            "\nMeaning: connection was established, but the server did not respond in time."
        )

    print("\nChecklist:")
    print("1. Is the MCP server running?")
    print("2. Is REVIT_MCP_URL correct?")
    print("3. If running from macOS host, try http://localhost:<port>/mcp instead of host.docker.internal.")
    print("4. If running from Docker, host.docker.internal may be correct.")
    print("5. Confirm with the dev team whether the transport is streamable-http, SSE, or stdio.")
    print("6. Confirm the exact endpoint path: /mcp, /sse, etc.")


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


async def check_tcp_reachable(url: str, timeout_seconds: float = 3.0) -> None:
    """
    Fast low-level check: can we open a TCP socket to host:port?
    This does not verify MCP correctness; it only verifies network reachability.
    """
    host, port = parse_host_port(url)
    print(host)
    print(port)

    def _connect() -> None:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass

    await asyncio.to_thread(_connect)

    print(f"TCP reachable: {host}:{port}")


async def list_mcp_tools() -> None:
    headers = {}
    if MCP_CONFIG.token:
        headers["Authorization"] = f"Bearer {MCP_CONFIG.token}"

    timeout = httpx.Timeout(
        connect=20.0,
        read=60.0,
        write=30.0,
        pool=20.0,
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
        verify=get_ssl_verify_config(MCP_CONFIG),
        cert=get_client_cert_config(MCP_CONFIG),
    ) as http_client:
        async with streamable_http_client(
            MCP_CONFIG.url,
            http_client=http_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools_response = await session.list_tools()

                if not tools_response.tools:
                    print("MCP server is reachable, but it returned no tools.")
                    return

                for tool in tools_response.tools:
                    print("\n" + "=" * 80)
                    print(f"NAME: {tool.name}")
                    print(f"DESCRIPTION: {tool.description}")
                    print("INPUT SCHEMA:")
                    print(json.dumps(tool.inputSchema, indent=2, ensure_ascii=False))


async def main() -> None:
    print(f"Using MCP_URL: {MCP_CONFIG.url}")
    if MCP_CONFIG.ca_bundle:
        print(f"Using MCP_CA_BUNDLE: {MCP_CONFIG.ca_bundle}")
    if MCP_CONFIG.client_cert:
        print(f"Using MCP_CLIENT_CERT: {MCP_CONFIG.client_cert}")

    try:
        await check_tcp_reachable(MCP_CONFIG.url)
        await list_mcp_tools()

    except BaseExceptionGroup as exc:
        print_exception_summary(exc)

    except (
        socket.timeout,
        TimeoutError,
        ConnectionRefusedError,
        OSError,
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.HTTPError,
    ) as exc:
        print_exception_summary(exc)

    except Exception as exc:
        print("\nUnexpected error.")
        print(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
