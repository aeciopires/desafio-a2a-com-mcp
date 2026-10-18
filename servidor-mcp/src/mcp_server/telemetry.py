"""OpenTelemetry setup. Optional: the service works the same with no collector around.

The W3C `traceparent` logged on stderr is the challenge requirement; spans exported
to Jaeger are an extra. Export runs in a background batch, never on the request path.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

logger = logging.getLogger(__name__)


class WarnOnceExporter(SpanExporter):
    """Wraps the OTLP exporter so an unreachable Jaeger yields one clear warning, not a flood."""

    def __init__(self, inner: SpanExporter, endpoint: str) -> None:
        self._inner = inner
        self._endpoint = endpoint
        self._failing = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self._inner.export(spans)
        except Exception as exc:  # noqa: BLE001 - exporter must never break the service
            result = SpanExportResult.FAILURE
            cause = str(exc)
        else:
            cause = "exporter returned FAILURE"
        if result is SpanExportResult.FAILURE and not self._failing:
            self._failing = True
            logger.warning(
                "OTLP export to %s failed: %s. Traces are disabled until Jaeger is reachable; "
                "requests are not affected.",
                self._endpoint,
                cause,
            )
        elif result is SpanExportResult.SUCCESS and self._failing:
            self._failing = False
            logger.info("OTLP export to %s recovered.", self._endpoint)
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def setup_tracing(service_name: str, version: str, endpoint: str | None, disabled: bool) -> TracerProvider | None:
    """Install a tracer provider. Spans always get real ids; export only when an endpoint is set."""
    if disabled:
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name, "service.version": version}),
        sampler=ParentBasedTraceIdRatio(1.0),
    )
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        # The OTLP exporter logs every failed batch; WarnOnceExporter reports it once instead.
        logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").setLevel(logging.CRITICAL)
        logging.getLogger("opentelemetry.exporter.otlp.proto.http._common").setLevel(logging.CRITICAL)
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces", timeout=5)
        provider.add_span_processor(BatchSpanProcessor(WarnOnceExporter(exporter, endpoint)))
    trace.set_tracer_provider(provider)
    return provider


tracer = trace.get_tracer("mcp_server")
