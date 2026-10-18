"""Entrypoint: `python -m mcp_server` (run from servidor-mcp/src or with PYTHONPATH=src)."""

from __future__ import annotations

import errno
import logging
import socket
import sys

import uvicorn

from mcp_server.config import ConfigError, load_settings
from mcp_server.logs import setup_logging
from mcp_server.telemetry import setup_tracing

logger = logging.getLogger("mcp_server")


def _ensure_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                raise ConfigError(
                    f"Port {port} is already in use on {host}. Set MCP_PORT to a free port "
                    f"(e.g. MCP_PORT={port + 10}) or stop the process holding it (ss -ltnp | grep {port})."
                ) from exc
            raise ConfigError(f"Cannot bind {host}:{port}: {exc.strerror}. Check MCP_HOST/MCP_PORT.") from exc


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[mcp-server] configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.service_name, settings.log_level, settings.log_format)
    try:
        _ensure_port_free(settings.host, settings.port)
    except ConfigError as exc:
        logger.error("startup failed: %s", exc)
        return 3

    provider = setup_tracing(settings.service_name, settings.version, settings.otlp_endpoint, settings.otel_disabled)

    from mcp_server.app import create_app

    app = create_app(settings)
    logger.info(
        "MCP server %s listening on http://%s:%d%s (data: %s, requestState TTL: %ds, tracing: %s)",
        settings.version,
        settings.host,
        settings.port,
        settings.path,
        settings.data_dir,
        settings.request_state_ttl,
        settings.otlp_endpoint or ("disabled" if settings.otel_disabled else "local only"),
    )
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_config=None, access_log=False)
    finally:
        if provider is not None:
            provider.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
