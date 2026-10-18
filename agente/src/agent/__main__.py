"""Entrypoint: `python -m agent` (run with PYTHONPATH=agente/src)."""

from __future__ import annotations

import errno
import logging
import socket
import sys

import uvicorn

from agent.config import ConfigError, load_settings
from agent.logs import setup_logging
from agent.telemetry import setup_tracing

logger = logging.getLogger("agent")


def _ensure_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                raise ConfigError(
                    f"Port {port} is already in use on {host}. Set AGENT_PORT to a free port "
                    f"(e.g. AGENT_PORT={port + 10}) or stop the process holding it (ss -ltnp | grep {port})."
                ) from exc
            raise ConfigError(f"Cannot bind {host}:{port}: {exc.strerror}. Check AGENT_HOST/AGENT_PORT.") from exc


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[agent] configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.service_name, settings.log_level, settings.log_format)
    try:
        _ensure_port_free(settings.host, settings.port)
    except ConfigError as exc:
        logger.error("startup failed: %s", exc)
        return 3

    provider = setup_tracing(settings.service_name, settings.version, settings.otlp_endpoint, settings.otel_disabled)

    from agent.app import create_app

    app = create_app(settings)
    logger.info(
        "A2A agent %s listening on http://%s:%d%s (card: /.well-known/agent-card.json, MCP: %s, tracing: %s)",
        settings.version,
        settings.host,
        settings.port,
        settings.path,
        settings.mcp_url,
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
