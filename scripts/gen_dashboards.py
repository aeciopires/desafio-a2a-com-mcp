#!/usr/bin/env python3
"""Generate the Grafana dashboards in observability/grafana/dashboards/ (stdlib only).

Edit the panel definitions here and run `make dashboards`; do not hand-edit the JSON.
Datasource UIDs are fixed (prometheus, jaeger, loki) by the provisioning file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "observability" / "grafana" / "dashboards"
# Grafana.com dashboard 24836, revision 1, downloaded as-is (see docs/observabilidade.md).
JAEGER_VENDORED = OUT.parent / "vendor" / "jaeger-v2-otel-metrics-24836-rev1.json"
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
JAEGER = {"type": "jaeger", "uid": "jaeger"}


class Layout:
    """Places panels left to right on Grafana's 24-column grid."""

    def __init__(self) -> None:
        self.x = self.y = self.row_h = 0
        self.next_id = 1

    def place(self, w: int, h: int) -> dict:
        if self.x + w > 24:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        pos = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.x += w
        self.row_h = max(self.row_h, h)
        return pos

    def pid(self) -> int:
        self.next_id += 1
        return self.next_id - 1


def target(expr: str, legend: str = "", exemplar: bool = False, instant: bool = False) -> dict:
    t = {"datasource": PROM, "expr": expr, "legendFormat": legend or "__auto", "refId": "A"}
    if exemplar:
        t["exemplar"] = True
    if instant:
        t["instant"], t["range"] = True, False
    return t


def with_refs(targets: list[dict]) -> list[dict]:
    for i, t in enumerate(targets):
        t["refId"] = chr(ord("A") + i)
    return targets


def timeseries(
    lay: Layout, title: str, targets: list[dict], unit: str = "short", w: int = 12, h: int = 8, desc: str = ""
) -> dict:
    return {
        "id": lay.pid(),
        "type": "timeseries",
        "title": title,
        "description": desc,
        "datasource": PROM,
        "gridPos": lay.place(w, h),
        "targets": with_refs(targets),
        "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 10}}, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
    }


def stat(lay: Layout, title: str, expr: str, unit: str = "short", w: int = 6, h: int = 4, desc: str = "") -> dict:
    return {
        "id": lay.pid(),
        "type": "stat",
        "title": title,
        "description": desc,
        "datasource": PROM,
        "gridPos": lay.place(w, h),
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"},
    }


def bars(lay: Layout, title: str, expr: str, legend: str, w: int = 12, h: int = 8, desc: str = "") -> dict:
    return {
        "id": lay.pid(),
        "type": "bargauge",
        "title": title,
        "description": desc,
        "datasource": PROM,
        "gridPos": lay.place(w, h),
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": "short", "min": 0}, "overrides": []},
        "options": {
            "orientation": "horizontal",
            "displayMode": "gradient",
            "showUnfilled": True,
            "reduceOptions": {"calcs": ["lastNotNull"]},
        },
    }


def table(lay: Layout, title: str, expr: str, w: int = 12, h: int = 8, desc: str = "") -> dict:
    return {
        "id": lay.pid(),
        "type": "table",
        "title": title,
        "description": desc,
        "datasource": PROM,
        "gridPos": lay.place(w, h),
        "targets": [{**target(expr, instant=True), "format": "table"}],
        "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True}}}],
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {"showHeader": True},
    }


def logs(lay: Layout, title: str, expr: str, w: int = 24, h: int = 10, desc: str = "") -> dict:
    return {
        "id": lay.pid(),
        "type": "logs",
        "title": title,
        "description": desc,
        "datasource": LOKI,
        "gridPos": lay.place(w, h),
        "targets": [{"datasource": LOKI, "expr": expr, "refId": "A"}],
        "options": {
            "showTime": True,
            "wrapLogMessage": True,
            "enableLogDetails": True,
            "sortOrder": "Descending",
            "prettifyLogMessage": False,
            "dedupStrategy": "none",
        },
    }


def traces(lay: Layout, title: str, w: int = 24, h: int = 12, desc: str = "") -> dict:
    return {
        "id": lay.pid(),
        "type": "traces",
        "title": title,
        "description": desc,
        "datasource": JAEGER,
        "gridPos": lay.place(w, h),
        "targets": [{"datasource": JAEGER, "query": "$trace_id", "refId": "A"}],
    }


def text(lay: Layout, content: str, w: int = 24, h: int = 3) -> dict:
    return {
        "id": lay.pid(),
        "type": "text",
        "title": "",
        "gridPos": lay.place(w, h),
        "options": {"mode": "markdown", "content": content},
    }


def dashboard(
    uid: str, title: str, panels: list[dict], variables: list[dict] | None = None, time_from: str = "now-1h"
) -> dict:
    return {
        "uid": uid,
        "title": title,
        "tags": ["central-de-salas"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "refresh": "10s",
        "time": {"from": time_from, "to": "now"},
        "templating": {"list": variables or []},
        "panels": panels,
        "links": [
            {
                "title": "Central de Salas",
                "type": "dashboards",
                "tags": ["central-de-salas"],
                "asDropdown": True,
                "includeVars": False,
                "keepTime": True,
            }
        ],
    }


def textbox(name: str, label: str, default: str = "") -> dict:
    return {
        "name": name,
        "label": label,
        "type": "textbox",
        "query": default,
        "current": {"text": default, "value": default},
        "hide": 0,
    }


def custom(name: str, label: str, values: list[str]) -> dict:
    options = [{"text": "All", "value": "$__all", "selected": True}] + [
        {"text": v, "value": v, "selected": False} for v in values
    ]
    return {
        "name": name,
        "label": label,
        "type": "custom",
        "query": ",".join(values),
        "includeAll": True,
        "allValue": ".*",
        "multi": False,
        "current": {"text": "All", "value": "$__all"},
        "options": options,
        "hide": 0,
    }


def business() -> dict:
    lay = Layout()
    total = "sum(reservations_created_total) or vector(0)"
    panels = [
        text(
            lay,
            "**Negocio**: reservas criadas em tempo de execucao (as do `dados/reservas.json` aparecem so "
            "na ocupacao). Os contadores voltam a zero a cada `make restore`.",
            h=2,
        ),
        stat(lay, "Reservas criadas", total),
        stat(lay, "Conflitos (input_required)", "sum(mrtr_input_required_total) or vector(0)"),
        stat(
            lay,
            "Taxa de conflito",
            'sum(mrtr_input_required_total) / (sum(mcp_requests_total{method="tools/call",name="reservar_sala"})'
            " - (sum(mrtr_retries_total) or vector(0)))",
            unit="percentunit",
            desc="Pedidos de reserva (sem contar os retries) que bateram em sala ocupada.",
        ),
        stat(
            lay,
            "Dia com mais reservas",
            "topk(1, sum by (date) (reservations_created_total))",
            desc="Valor = numero de reservas; o dia aparece no rotulo.",
        ),
        bars(lay, "Reservas por sala", "sum by (room) (reservations_created_total)", "{{room}}"),
        bars(lay, "Reservas por responsavel", "sum by (responsible) (reservations_created_total)", "{{responsible}}"),
        table(lay, "Reservas por data", "sort_desc(sum by (date) (reservations_created_total))"),
        bars(
            lay, "Ocupacao atual por sala (inclui reservas iniciais)", "sum by (room) (reservations_active)", "{{room}}"
        ),
        timeseries(
            lay,
            "Aceites x recusas na escolha de alternativa",
            [target("sum by (action) (increase(mrtr_retries_total[5m]))", "{{action}}")],
        ),
        timeseries(
            lay,
            "Erros de regra de negocio por motivo",
            [target("sum by (reason) (increase(mcp_tool_errors_total[5m]))", "{{reason}}")],
        ),
    ]
    return dashboard("central-de-salas-negocio", "Central de Salas - Negocio", panels, time_from="now-6h")


def agent() -> dict:
    lay = Layout()
    panels = [
        stat(
            lay,
            "Confirmacoes pendentes (INPUT_REQUIRED)",
            'sum(a2a_tasks_by_state{state="TASK_STATE_INPUT_REQUIRED"}) or vector(0)',
        ),
        stat(lay, "Tasks concluidas", 'sum(a2a_tasks_total{final_state="TASK_STATE_COMPLETED"}) or vector(0)'),
        stat(lay, "Tasks com falha", 'sum(a2a_tasks_total{final_state="TASK_STATE_FAILED"}) or vector(0)'),
        stat(
            lay,
            "Chamadas MCP por Task",
            "sum(agent_mcp_calls_total) / sum(a2a_tasks_total)",
            unit="none",
            desc="Sem LLM: estas sao as 'chamadas ao modelo' deste agente.",
        ),
        bars(lay, "Tasks por estado atual", "sum by (state) (a2a_tasks_by_state)", "{{state}}"),
        timeseries(
            lay,
            "Tasks finalizadas por estado",
            [target("sum by (final_state) (increase(a2a_tasks_total[5m]))", "{{final_state}}")],
        ),
        timeseries(
            lay,
            "Latencia A2A (p50/p95) - clique no exemplar para abrir o trace",
            [
                target(
                    "histogram_quantile(0.5, sum by (le) (rate(a2a_request_duration_seconds_bucket[5m])))",
                    "p50",
                    exemplar=True,
                ),
                target(
                    "histogram_quantile(0.95, sum by (le) (rate(a2a_request_duration_seconds_bucket[5m])))",
                    "p95",
                    exemplar=True,
                ),
            ],
            unit="s",
        ),
        timeseries(
            lay,
            "Chamadas MCP do agente por metodo e resultado",
            [
                target(
                    "sum by (method, name, result_type) (rate(agent_mcp_calls_total[1m]))",
                    "{{method}} {{name}} {{result_type}}",
                )
            ],
            unit="reqps",
        ),
        timeseries(
            lay,
            "Latencia das chamadas MCP (p95)",
            [
                target(
                    "histogram_quantile(0.95, sum by (le, method) (rate(agent_mcp_call_duration_seconds_bucket[5m])))",
                    "{{method}}",
                    exemplar=True,
                )
            ],
            unit="s",
        ),
        timeseries(
            lay,
            "Requisicoes A2A por metodo e resultado",
            [target("sum by (method, outcome) (rate(a2a_requests_total[1m]))", "{{method}} {{outcome}}")],
            unit="reqps",
        ),
        logs(lay, "Logs do agente", '{service="agent"} | json | task_id=~"$task_id"'),
    ]
    return dashboard(
        "central-de-salas-agente",
        "Central de Salas - Agente A2A",
        panels,
        [textbox("task_id", "Task id (regex)", ".*")],
    )


def mcp() -> dict:
    lay = Layout()
    panels = [
        timeseries(
            lay,
            "Requisicoes MCP por metodo",
            [target("sum by (method, name) (rate(mcp_requests_total[1m]))", "{{method}} {{name}}")],
            unit="reqps",
        ),
        timeseries(
            lay,
            "Latencia por tool (p95) com exemplars",
            [
                target(
                    "histogram_quantile(0.95, sum by (le, method, name) "
                    "(rate(mcp_request_duration_seconds_bucket[5m])))",
                    "{{method}} {{name}}",
                    exemplar=True,
                )
            ],
            unit="s",
        ),
        timeseries(
            lay,
            "Erros de protocolo por codigo",
            [target("sum by (code) (increase(mcp_protocol_errors_total[5m]))", "{{code}}")],
            w=8,
        ),
        timeseries(
            lay,
            "requestState rejeitados por motivo",
            [target("sum by (reason) (increase(request_state_rejected_total[5m]))", "{{reason}}")],
            w=8,
        ),
        timeseries(
            lay,
            "Resultados por tipo",
            [target("sum by (outcome) (increase(mcp_requests_total[5m]))", "{{outcome}}")],
            w=8,
        ),
        logs(
            lay,
            "Logs do servidor MCP (stderr)",
            '{service="mcp-server"} | json | method=~"$method" | trace_id=~"$trace_id"',
        ),
    ]
    variables = [
        custom("method", "Metodo", ["tools/list", "tools/call", "resources/read"]),
        textbox("trace_id", "Trace id (regex)", ".*"),
    ]
    return dashboard("central-de-salas-mcp", "Central de Salas - MCP e protocolo", panels, variables)


def correlation() -> dict:
    lay = Layout()
    panels = [
        text(
            lay,
            "Cole no campo **trace_id** o valor que o validador imprime na primeira linha "
            "(`trace-id desta execucao: ...`). Os logs abaixo mostram os dois servicos; o painel de trace "
            "mostra a arvore de spans. Em um log, use **Ver trace no Jaeger**; em um span, **Logs for this "
            "span**.",
            h=3,
        ),
        logs(
            lay,
            "Logs do agente e do servidor MCP para o trace",
            '{service=~"agent|mcp-server"} | trace_id="$trace_id"',
            h=10,
        ),
        traces(lay, "Trace no Jaeger", h=14),
        timeseries(
            lay,
            "Latencia A2A e MCP (exemplars ligam ao trace)",
            [
                target(
                    "histogram_quantile(0.95, sum by (le) (rate(a2a_request_duration_seconds_bucket[5m])))",
                    "A2A p95",
                    exemplar=True,
                ),
                target(
                    "histogram_quantile(0.95, sum by (le) (rate(mcp_request_duration_seconds_bucket[5m])))",
                    "MCP p95",
                    exemplar=True,
                ),
            ],
            unit="s",
        ),
        timeseries(
            lay,
            "Requisicoes por servico",
            [
                target("sum(rate(a2a_requests_total[1m]))", "agent"),
                target("sum(rate(mcp_requests_total[1m]))", "mcp-server"),
            ],
            unit="reqps",
        ),
    ]
    return dashboard(
        "central-de-salas-correlacao",
        "Central de Salas - Correlacao (metricas, traces e logs)",
        panels,
        [textbox("trace_id", "Trace id", "")],
        time_from="now-30m",
    )


def _any_counter_suffix(expr: str) -> str:
    """`otelcol_x_total{a="b"}` -> `{__name__=~"otelcol_x(_total)?", a="b"}`.

    Jaeger 2.22's internal Prometheus exporter drops the `_total` suffix the upstream
    dashboard expects; matching both names keeps it working before and after a fix.
    """

    def repl(m: re.Match[str]) -> str:
        matchers = f", {m.group(3)}" if m.group(3) else ""
        return f'{{__name__=~"{m.group(1)}(_total)?"{matchers}}}'

    return re.sub(r"\b(otelcol_\w+?)_total(\{([^}]*)\})?", repl, expr)


def jaeger_internal() -> dict:
    """Grafana.com dashboard 24836 (Jaeger V2 OpenTelemetry Metrics), adapted to this stack.

    The upstream JSON is vendored untouched in observability/grafana/vendor/; only the
    datasource default, the counter names, uid/tags and the cross-dashboard link change here.
    """
    d = json.loads(JAEGER_VENDORED.read_text(encoding="utf-8"))
    d.pop("__inputs", None)
    d.pop("__requires", None)
    for var in d["templating"]["list"]:
        if var["name"] == "ds_prometheus":
            var["current"] = {"text": "Prometheus", "value": PROM["uid"]}

    def walk(panels: list[dict]) -> None:
        for panel in panels:
            for t in panel.get("targets", []):
                if "expr" in t:
                    t["expr"] = _any_counter_suffix(t["expr"])
            walk(panel.get("panels", []))

    walk(d["panels"])
    d |= {
        "uid": "jaeger-v2-otel-metrics",
        "id": None,
        "editable": False,
        "refresh": "10s",
        "tags": ["central-de-salas", "jaeger"],
        "links": dashboard("", "", [])["links"],
    }
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {"negocio": business, "agente": agent, "mcp": mcp, "correlacao": correlation, "jaeger": jaeger_internal}
    for name, build in builders.items():
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(OUT.parents[2])}")


if __name__ == "__main__":
    main()
