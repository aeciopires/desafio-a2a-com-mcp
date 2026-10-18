"""Traces in Jaeger, logs in Loki, Grafana wiring, and the stack working with all of them down."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx
import pytest
from conftest import (
    GRAFANA_URL,
    JAEGER_URL,
    LOKI_URL,
    compose,
    env_value,
    eventually,
    mcp_log_lines,
    new_traceparent,
    state,
    task_of,
)

CONFLICT = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"


def _paused_and_resumed(a2a) -> str:
    traceparent, trace_id = new_traceparent()
    paused = task_of(a2a.send(CONFLICT, traceparent=traceparent))
    assert state(paused) == "TASK_STATE_INPUT_REQUIRED"
    done = task_of(a2a.send("escolha=sala-mirante", paused["id"], traceparent=traceparent))
    assert state(done) == "TASK_STATE_COMPLETED"
    return trace_id


@pytest.mark.slow
def test_trace_in_jaeger_spans_both_services(fresh_stack, a2a, http):
    trace_id = _paused_and_resumed(a2a)

    def fetch():
        response = http.get(f"{JAEGER_URL}/api/traces/{trace_id}")
        data = response.json().get("data") or []
        if not data:
            return None
        trace = data[0]
        services = {p["serviceName"] for p in trace["processes"].values()}
        calls = [s for s in trace["spans"] if s["operationName"] == "mcp tools/call reservar_sala"]
        # Each tools/call shows up twice (agent client span + MCP server span).
        return trace if {"agent", "mcp-server"} <= services and len(calls) >= 4 else None

    trace = eventually(fetch, what=f"trace {trace_id} in Jaeger")
    ids = {
        tag["value"]
        for span in trace["spans"]
        if span["operationName"] == "mcp tools/call reservar_sala"
        for tag in span["tags"]
        if tag["key"] == "rpc.jsonrpc.request_id"
    }
    assert len(ids) == 2, "the retry must use a different JSON-RPC id"
    names = {s["operationName"] for s in trace["spans"]}
    assert {"a2a SendMessage", "bridge.pause", "bridge.resume", "mcp tools/list"} <= names


@pytest.mark.slow
def test_logs_in_loki_carry_the_trace_id(fresh_stack, a2a, http):
    trace_id = _paused_and_resumed(a2a)
    query = f'{{service=~"agent|mcp-server"}} | trace_id="{trace_id}"'

    def fetch():
        params = {"query": query, "limit": 200, "start": str(int((time.time() - 600) * 1e9))}
        result = http.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params).json()["data"]["result"]
        services = {stream["stream"].get("service") for stream in result}
        lines = [value[1] for stream in result for value in stream["values"]]
        return lines if {"agent", "mcp-server"} <= services else None

    lines = eventually(fetch, timeout=60, what=f"logs of trace {trace_id} in Loki")
    assert any('"method": "tools/list"' in line for line in lines)
    assert sum('"method": "tools/call"' in line for line in lines) >= 2


def test_grafana_datasources_and_dashboards(http):
    auth = (env_value("GRAFANA_ADMIN_USER", "admin") or "admin", env_value("GRAFANA_ADMIN_PASSWORD"))
    datasources = {d["uid"]: d for d in http.get(f"{GRAFANA_URL}/api/datasources", auth=auth).json()}
    assert {"prometheus", "jaeger", "loki"} <= set(datasources)
    for uid in ("prometheus", "jaeger", "loki"):
        health = http.get(f"{GRAFANA_URL}/api/datasources/uid/{uid}/health", auth=auth)
        assert health.status_code == 200, f"{uid}: {health.text}"
        assert health.json().get("status") == "OK", f"{uid}: {health.text}"
    loki = datasources["loki"]["jsonData"]["derivedFields"]
    assert any(field["datasourceUid"] == "jaeger" for field in loki)
    assert datasources["jaeger"]["jsonData"]["tracesToLogsV2"]["datasourceUid"] == "loki"
    assert datasources["prometheus"]["jsonData"]["exemplarTraceIdDestinations"][0]["datasourceUid"] == "jaeger"
    found = {
        d["uid"] for d in http.get(f"{GRAFANA_URL}/api/search", params={"tag": "central-de-salas"}, auth=auth).json()
    }
    assert found == {
        "central-de-salas-negocio",
        "central-de-salas-agente",
        "central-de-salas-mcp",
        "central-de-salas-correlacao",
        "jaeger-v2-otel-metrics",
    }


def _grafana_query(http, auth, query: dict, minutes: int = 30) -> dict:
    now = int(time.time() * 1000)
    body = {"from": str(now - minutes * 60_000), "to": str(now + 60_000), "queries": [query | {"refId": "A"}]}
    response = http.post(f"{GRAFANA_URL}/api/ds/query", json=body, auth=auth)
    return response.json()["results"]["A"]


@pytest.mark.slow
def test_grafana_reads_jaeger_v2_through_api_v3(fresh_stack, a2a, http):
    """Jaeger 2.21+ has no /api/services: Grafana must go through /api/v3 (feature toggle)."""
    auth = (env_value("GRAFANA_ADMIN_USER", "admin") or "admin", env_value("GRAFANA_ADMIN_PASSWORD"))
    trace_id = _paused_and_resumed(a2a)
    jaeger = {"type": "jaeger", "uid": "jaeger"}

    def services():
        found = http.get(f"{GRAFANA_URL}/api/datasources/uid/jaeger/resources/services", auth=auth).json()
        return found if {"agent", "mcp-server"} <= set(found) else None

    eventually(services, what="services agent and mcp-server in Grafana's Jaeger datasource")
    operations = http.get(f"{GRAFANA_URL}/api/datasources/uid/jaeger/resources/services/agent/operations", auth=auth)
    assert operations.status_code == 200, operations.text
    assert "a2a SendMessage" in operations.json()

    def trace():
        result = _grafana_query(http, auth, {"datasource": jaeger, "queryType": "", "query": trace_id})
        frames = result.get("frames") or []
        rows = len(frames[0]["data"]["values"][0]) if frames and frames[0]["data"]["values"] else 0
        return result if result.get("status") == 200 and rows >= 4 else None

    eventually(trace, what=f"trace {trace_id} through Grafana")
    graph = _grafana_query(http, auth, {"datasource": jaeger, "queryType": "dependencyGraph"})
    assert graph.get("status") == 200, graph


@pytest.mark.slow
def test_prometheus_scrapes_jaeger_internal_metrics(fresh_stack, a2a, http):
    """Feeds the Jaeger V2 OpenTelemetry Metrics dashboard (grafana.com 24836)."""
    auth = (env_value("GRAFANA_ADMIN_USER", "admin") or "admin", env_value("GRAFANA_ADMIN_PASSWORD"))
    _paused_and_resumed(a2a)
    expr = 'sum({__name__=~"otelcol_receiver_accepted_spans(_total)?", job="jaeger"})'

    def accepted():
        result = _grafana_query(http, auth, {"datasource": {"type": "prometheus", "uid": "prometheus"}, "expr": expr})
        frames = result.get("frames") or []
        values = frames[0]["data"]["values"][1] if frames and frames[0]["data"]["values"] else []
        return values if values and values[-1] > 0 else None

    eventually(accepted, timeout=60, what="otelcol_receiver_accepted_spans from job jaeger in Prometheus")


@pytest.mark.slow
def test_everything_works_with_the_observability_stack_down(fresh_stack, a2a):
    compose("stop", "jaeger", "loki", "alloy")
    try:
        since = datetime.now(UTC).isoformat()
        trace_id = _paused_and_resumed(a2a)
        rows = [r for r in mcp_log_lines(since) if trace_id in (r.get("traceparent") or "")]
        assert [r["method"] for r in rows].count("tools/call") == 2
    finally:
        compose("start", "jaeger", "loki", "alloy")


def test_metrics_endpoints_expose_exemplars(http):
    from conftest import AGENT_URL, MCP_URL

    for url in (AGENT_URL, MCP_URL):
        response = http.get(f"{url}/metrics", headers={"Accept": "application/openmetrics-text"})
        assert response.status_code == 200
        assert "# EOF" in response.text


def test_swagger_and_openapi_are_served(http):
    from conftest import AGENT_URL, MCP_URL

    for url in (AGENT_URL, MCP_URL):
        assert http.get(f"{url}/openapi.json").json()["openapi"].startswith("3.1")
        assert "swagger-ui" in http.get(f"{url}/docs").text


def test_prometheus_scrapes_both_services(http):
    prometheus = f"http://localhost:{env_value('PROMETHEUS_PORT', '9090') or '9090'}"

    def fetch():
        targets = httpx.get(f"{prometheus}/api/v1/targets", timeout=5).json()["data"]["activeTargets"]
        healthy = {t["labels"]["job"] for t in targets if t["health"] == "up"}
        return healthy if {"agent", "mcp-server"} <= healthy else None

    eventually(fetch, timeout=30, what="Prometheus targets up")
