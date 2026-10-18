"""Structured logging to stderr: one JSON object per line, with trace correlation.

Every line carries `trace_id`/`span_id` (from the active span, or from fields the
caller passes explicitly), which is what Loki and Grafana use to jump to Jaeger.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

_RESERVED = set(vars(logging.makeLogRecord({})))


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _RESERVED and not k.startswith("_")})
        if "trace_id" not in payload:
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                payload["trace_id"] = format(ctx.trace_id, "032x")
                payload["span_id"] = format(ctx.span_id, "016x")
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = {k: v for k, v in vars(record).items() if k not in _RESERVED and not k.startswith("_")}
        tail = " ".join(f"{k}={v}" for k, v in extras.items())
        base = f"{datetime.now(UTC).strftime('%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()}"
        return f"{base} {tail}".rstrip()


def setup_logging(service: str, level: str, fmt: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter(service) if fmt == "json" else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Uvicorn access logs would duplicate the MCP request log; keep only its errors.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
