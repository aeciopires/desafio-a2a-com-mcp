"""Span hierarchy of one paused-and-resumed booking, captured in memory."""

from __future__ import annotations

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from tests.conftest import MCP_URL, REQUEST_STATE, booked, input_required

from agent.app import create_app
from agent.config import load_settings
from agent.telemetry import WarnOnceExporter

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
CONFLICT = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"


@pytest.fixture
async def a2a(monkeypatch, fake_mcp):
    monkeypatch.setenv("MCP_URL", MCP_URL)
    EXPORTER.clear()
    app = create_app(load_settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent.test") as client:
        yield client


async def send(client, text, task_id=None, traceparent=None):
    message = {"messageId": "m", "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    headers = {"traceparent": traceparent} if traceparent else {}
    body = {"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": message}}
    return (await client.post("/a2a", json=body, headers=headers)).json()["result"]["task"]


async def test_pause_and_resume_stay_in_the_client_trace(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca"]), booked("sala-fusca")]
    task = await send(a2a, CONFLICT, traceparent=f"00-{TRACE_ID}-00f067aa0ba902b7-01")
    await send(a2a, "escolha=sala-fusca", task["id"])  # no header: the Task context is reused

    spans = EXPORTER.get_finished_spans()
    names = [s.name for s in spans]
    assert names.count("a2a SendMessage") == 2
    assert "bridge.pause" in names and "bridge.resume" in names
    assert names.count("mcp tools/call reservar_sala") == 2
    assert {format(s.context.trace_id, "032x") for s in spans} == {TRACE_ID}

    # The traceparent in each MCP _meta is the client span that sent it.
    client_spans = [s for s in spans if s.name.startswith("mcp ")]
    sent = [r["params"]["_meta"]["traceparent"] for r in fake_mcp.requests]
    assert [f"00-{s.context.trace_id:032x}-{s.context.span_id:016x}-01" for s in client_spans] == sent

    retry = next(s for s in client_spans if s.attributes.get("mcp.retry") == "true")
    assert retry.attributes["mcp.result_type"] == "complete"


async def test_request_state_is_never_a_span_attribute(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca"]), booked("sala-fusca")]
    task = await send(a2a, CONFLICT)
    await send(a2a, "escolha=sala-fusca", task["id"])
    for span in EXPORTER.get_finished_spans():
        assert all(REQUEST_STATE not in str(v) for v in span.attributes.values())


class _Failing(InMemorySpanExporter):
    def export(self, spans):
        return SpanExportResult.FAILURE


def test_unreachable_collector_is_reported_once(caplog):
    exporter = WarnOnceExporter(_Failing(), "http://jaeger:4318")
    exporter.export([])
    exporter.export([])
    warnings = [r for r in caplog.records if "OTLP export to http://jaeger:4318 failed" in r.getMessage()]
    assert len(warnings) == 1


async def test_a2a_latency_histogram_carries_the_trace_exemplar(a2a, fake_mcp):
    fake_mcp.tool_results = [booked("sala-garagem")]
    await send(a2a, CONFLICT, traceparent=f"00-{TRACE_ID}-00f067aa0ba902b7-01")
    text = (await a2a.get("/metrics", headers={"Accept": "application/openmetrics-text"})).text
    lines = [line for line in text.splitlines() if line.startswith("a2a_request_duration_seconds_bucket")]
    assert any(f'trace_id="{TRACE_ID}"' in line for line in lines)
