import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_MCP_CONFIG_PATH = Path(__file__).resolve().parents[1] / "mcp_config.yaml"


@dataclass(frozen=True)
class McpConnectionConfig:
    url: str
    tool: str
    token: str = ""
    ca_bundle: str = ""
    client_cert: str = ""
    client_key: str = ""
    insecure_ssl: bool = False


def _resolve_path(value: str, config_path: Path) -> str:
    if not value:
        return ""

    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)

    return str((config_path.parent / path).resolve())


def _read_config_file() -> tuple[dict[str, Any], Path]:
    config_path = Path(os.getenv("REVIT_MCP_CONFIG", DEFAULT_MCP_CONFIG_PATH)).expanduser()
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path

    with config_path.open(encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"MCP config must be a YAML mapping: {config_path}")

    mcp_data = data.get("mcp", data)
    if not isinstance(mcp_data, dict):
        raise ValueError(f"MCP config 'mcp' section must be a YAML mapping: {config_path}")

    return mcp_data, config_path


def get_mcp_config() -> McpConnectionConfig:
    data, config_path = _read_config_file()

    url = str(data.get("url") or "").strip()
    tool = str(data.get("tool") or "").strip()
    if not url:
        raise ValueError(f"MCP config is missing 'url': {config_path}")
    if not tool:
        raise ValueError(f"MCP config is missing 'tool': {config_path}")

    return McpConnectionConfig(
        url=url,
        tool=tool,
        token=str(data.get("token") or ""),
        ca_bundle=_resolve_path(str(data.get("ca_bundle") or ""), config_path),
        client_cert=_resolve_path(str(data.get("client_cert") or ""), config_path),
        client_key=_resolve_path(str(data.get("client_key") or ""), config_path),
        insecure_ssl=bool(data.get("insecure_ssl", False)),
    )


def get_ssl_verify_config(config: McpConnectionConfig | None = None) -> bool | str:
    config = config or get_mcp_config()
    if config.insecure_ssl:
        return False

    if config.ca_bundle:
        return config.ca_bundle

    return True


def get_client_cert_config(config: McpConnectionConfig | None = None) -> str | tuple[str, str] | None:
    config = config or get_mcp_config()

    if config.client_cert and config.client_key:
        return config.client_cert, config.client_key

    if config.client_cert:
        return config.client_cert

    if config.client_key:
        raise ValueError("MCP config has 'client_key', but 'client_cert' is missing.")

    return None
