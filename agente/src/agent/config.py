"""Runtime settings read from environment variables, validated at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

SERVICE_NAME = "agent"
CLIENT_NAME = "agente-central-de-salas"


class ConfigError(Exception):
    """A setting is missing or invalid. The message tells the operator how to fix it."""


def get_version() -> str:
    """Return the project version from the VERSION file (single source of truth)."""
    explicit = os.environ.get("VERSION_FILE")
    candidates = [Path(explicit)] if explicit else []
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        candidates.extend(directory / "VERSION" for directory in (start, *start.parents))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    return "0.0.0+unknown"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    path: str
    public_url: str
    mcp_url: str
    mcp_timeout: float
    log_level: str
    log_format: str
    otlp_endpoint: str | None
    otel_disabled: bool
    service_name: str
    version: str


def load_settings() -> Settings:
    """Build the settings from the environment, failing fast with actionable messages."""
    port = _int_env("AGENT_PORT", 7300)
    if not 1 <= port <= 65535:
        raise ConfigError(f"AGENT_PORT must be a valid TCP port (1-65535), got {port}")

    path = os.environ.get("AGENT_PATH", "/a2a").strip() or "/a2a"
    if not path.startswith("/"):
        raise ConfigError(f"AGENT_PATH must start with '/', got {path!r}")

    public_url = os.environ.get("AGENT_PUBLIC_URL", "").strip() or f"http://127.0.0.1:{port}{path}"
    mcp_port = _int_env("MCP_PORT", 7301)
    mcp_url = os.environ.get("MCP_URL", "").strip() or f"http://127.0.0.1:{mcp_port}/mcp"
    for name, value in (("AGENT_PUBLIC_URL", public_url), ("MCP_URL", mcp_url)):
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError(f"{name} must be an absolute http(s) URL, got {value!r}")

    timeout = _float_env("MCP_TIMEOUT_SECONDS", 10.0)
    if timeout <= 0:
        raise ConfigError(f"MCP_TIMEOUT_SECONDS must be positive, got {timeout}")

    log_format = os.environ.get("LOG_FORMAT", "json").strip().lower() or "json"
    if log_format not in {"json", "text"}:
        raise ConfigError(f"LOG_FORMAT must be 'json' or 'text', got {log_format!r}")

    return Settings(
        host=os.environ.get("AGENT_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=port,
        path=path,
        public_url=public_url,
        mcp_url=mcp_url,
        mcp_timeout=timeout,
        log_level=(os.environ.get("LOG_LEVEL", "INFO").strip() or "INFO").upper(),
        log_format=log_format,
        otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() or None,
        otel_disabled=_bool_env("OTEL_SDK_DISABLED", False),
        service_name=os.environ.get("OTEL_SERVICE_NAME", SERVICE_NAME).strip() or SERVICE_NAME,
        version=get_version(),
    )
