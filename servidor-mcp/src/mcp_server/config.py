"""Runtime settings read from environment variables, validated at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_NAME = "mcp-server"
SERVER_NAME = "central-de-salas"

MIN_SECRET_BYTES = 32
MIN_TTL_SECONDS = 300
MAX_TTL_SECONDS = 1800


class ConfigError(Exception):
    """A setting is missing or invalid. The message tells the operator how to fix it."""


def _find_version_file() -> Path | None:
    explicit = os.environ.get("VERSION_FILE")
    if explicit:
        return Path(explicit)
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for directory in (start, *start.parents):
            candidate = directory / "VERSION"
            if candidate.is_file():
                return candidate
    return None


def get_version() -> str:
    """Return the project version from the VERSION file (single source of truth)."""
    path = _find_version_file()
    if path is None or not path.is_file():
        return "0.0.0+unknown"
    return path.read_text(encoding="utf-8").strip()


def _find_data_dir() -> Path:
    explicit = os.environ.get("DATA_DIR")
    if explicit:
        return Path(explicit)
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for directory in (start, *start.parents):
            candidate = directory / "dados"
            if (candidate / "salas.json").is_file():
                return candidate
    return Path("dados")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


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
    data_dir: Path
    request_state_secret: str
    request_state_ttl: int
    log_level: str
    log_format: str
    otlp_endpoint: str | None
    otel_disabled: bool
    service_name: str
    version: str


def load_settings() -> Settings:
    """Build the settings from the environment, failing fast with actionable messages."""
    secret = os.environ.get("REQUEST_STATE_SECRET", "").strip()
    if not secret:
        raise ConfigError(
            "REQUEST_STATE_SECRET is not set. Generate one with `make secret` "
            '(or: python3 -c "import secrets; print(secrets.token_hex(32))") and export it.'
        )
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise ConfigError(
            f"REQUEST_STATE_SECRET must be at least {MIN_SECRET_BYTES} bytes (64 hex chars); "
            f"got {len(secret.encode())}. Generate one with: make secret"
        )

    ttl = _int_env("REQUEST_STATE_TTL_SECONDS", 600)
    if not MIN_TTL_SECONDS <= ttl <= MAX_TTL_SECONDS:
        raise ConfigError(
            f"REQUEST_STATE_TTL_SECONDS must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS}, got {ttl}"
        )

    port = _int_env("MCP_PORT", 7301)
    if not 1 <= port <= 65535:
        raise ConfigError(f"MCP_PORT must be a valid TCP port (1-65535), got {port}")

    path = os.environ.get("MCP_PATH", "/mcp").strip() or "/mcp"
    if not path.startswith("/"):
        raise ConfigError(f"MCP_PATH must start with '/', got {path!r}")

    data_dir = _find_data_dir()
    for required in ("salas.json", "reservas.json", "politica-de-uso.md"):
        if not (data_dir / required).is_file():
            raise ConfigError(
                f"Data file {data_dir / required} not found. Run from the repository root or set DATA_DIR."
            )

    log_format = os.environ.get("LOG_FORMAT", "json").strip().lower() or "json"
    if log_format not in {"json", "text"}:
        raise ConfigError(f"LOG_FORMAT must be 'json' or 'text', got {log_format!r}")

    return Settings(
        host=os.environ.get("MCP_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=port,
        path=path,
        data_dir=data_dir,
        request_state_secret=secret,
        request_state_ttl=ttl,
        log_level=(os.environ.get("LOG_LEVEL", "INFO").strip() or "INFO").upper(),
        log_format=log_format,
        otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() or None,
        otel_disabled=_bool_env("OTEL_SDK_DISABLED", False),
        service_name=os.environ.get("OTEL_SERVICE_NAME", SERVICE_NAME).strip() or SERVICE_NAME,
        version=get_version(),
    )
