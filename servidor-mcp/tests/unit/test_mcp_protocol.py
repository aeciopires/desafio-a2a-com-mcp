"""Protocol tests against the real ASGI app, in process (no network, no Docker)."""

from __future__ import annotations

import contextlib
import json
import logging
import secrets
from collections.abc import AsyncIterator

import httpx
import pytest

from mcp_server.app import create_app
from mcp_server.config import load_settings

PROTOCOL = "2026-07-28"
CAPS = {"elicitation": {"form": {}}}
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
CONFLICT = {
    "sala": "sala-garagem",
    "inicio": "2026-11-03T14:00:00-03:00",
    "fim": "2026-11-03T15:00:00-03:00",
    "responsavel": "Marty",
}


@contextlib.asynccontextmanager
async def mcp_client(secret: str | None = None) -> AsyncIterator[httpx.AsyncClient]:
    if secret:
        import os

        os.environ["REQUEST_STATE_SECRET"] = secret
    app = create_app(load_settings())
    starlette_app = app.app
    async with starlette_app.router.lifespan_context(starlette_app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7301") as client:
            yield client


async def rpc(
    client: httpx.AsyncClient,
    method: str,
    params: dict,
    name: str | None = None,
    caps: dict | None = None,
    meta_override: dict | None = None,
    headers_override: dict | None = None,
) -> tuple[int, dict]:
    meta = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL,
        "io.modelcontextprotocol/clientCapabilities": CAPS if caps is None else caps,
        "traceparent": TRACEPARENT,
    }
    if meta_override is not None:
        meta = meta_override
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
        "Mcp-Method": method,
    }
    if name:
        headers["Mcp-Name"] = name
    headers.update(headers_override or {})
    body = {"jsonrpc": "2.0", "id": secrets.token_hex(4), "method": method, "params": {**params, "_meta": meta}}
    response = await client.post("/mcp", json=body, headers=headers)
    return response.status_code, response.json()


async def book(client, args, **kw):
    return await rpc(client, "tools/call", {"name": "reservar_sala", "arguments": args}, "reservar_sala", **kw)


async def retry(client, args, key, answer, state):
    params = {"name": "reservar_sala", "arguments": args, "inputResponses": {key: answer}, "requestState": state}
    return await rpc(client, "tools/call", params, "reservar_sala")


async def test_tools_list_has_three_tools_with_object_schemas():
    async with mcp_client() as client:
        status, body = await rpc(client, "tools/list", {})
    tools = {t["name"]: t for t in body["result"]["tools"]}
    assert status == 200
    assert set(tools) == {"listar_salas", "consultar_disponibilidade", "reservar_sala"}
    assert all(t["inputSchema"]["type"] == "object" for t in tools.values())
    assert "escolha" not in tools["reservar_sala"]["inputSchema"]["properties"]


async def test_listar_salas_text_matches_structured_content():
    async with mcp_client() as client:
        _, body = await rpc(client, "tools/call", {"name": "listar_salas", "arguments": {}}, "listar_salas")
    result = body["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert len(result["structuredContent"]["salas"]) == 5


@pytest.mark.parametrize(
    "missing", ["io.modelcontextprotocol/protocolVersion", "io.modelcontextprotocol/clientCapabilities"]
)
async def test_missing_meta_is_rejected_with_400(missing):
    meta = {"io.modelcontextprotocol/protocolVersion": PROTOCOL, "io.modelcontextprotocol/clientCapabilities": CAPS}
    meta.pop(missing)
    async with mcp_client() as client:
        status, body = await rpc(client, "tools/list", {}, meta_override=meta)
    assert (status, body["error"]["code"]) == (400, -32602)


async def test_header_that_does_not_match_the_body_is_rejected():
    async with mcp_client() as client:
        _, body = await rpc(client, "tools/list", {}, headers_override={"Mcp-Method": "tools/call"})
    assert body["error"]["code"] == -32020


async def test_policy_resource_and_unknown_uri():
    async with mcp_client() as client:
        _, ok = await rpc(client, "resources/read", {"uri": "politica://uso"}, "politica://uso")
        status, missing = await rpc(client, "resources/read", {"uri": "politica://nada"}, "politica://nada")
    content = ok["result"]["contents"][0]
    assert content["mimeType"] == "text/markdown"
    assert content["text"].startswith("versao: 2026-11-01")
    assert missing["error"]["code"] == -32602


async def test_free_room_is_booked_with_policy_version():
    args = {
        **CONFLICT,
        "sala": "sala-aquario",
        "inicio": "2026-11-03T09:00:00-03:00",
        "fim": "2026-11-03T10:00:00-03:00",
    }
    async with mcp_client() as client:
        _, body = await book(client, args)
    data = body["result"]["structuredContent"]
    assert body["result"]["resultType"] == "complete"
    assert data | {"reserva": None} == {
        "reserva": None,
        "reservado": True,
        "sala": "sala-aquario",
        "inicio": args["inicio"],
        "fim": args["fim"],
        "responsavel": "Marty",
        "politica": "2026-11-01",
        "motivo": None,
    }


async def test_mrtr_full_cycle_accept():
    async with mcp_client() as client:
        _, first = await book(client, CONFLICT)
        result = first["result"]
        assert result["resultType"] == "input_required"
        ((key, request),) = result["inputRequests"].items()
        assert request["method"] == "elicitation/create"
        assert request["params"]["mode"] == "form"
        assert request["params"]["requestedSchema"]["properties"]["sala"]["enum"] == ["sala-fusca", "sala-mirante"]

        _, second = await retry(
            client, CONFLICT, key, {"action": "accept", "content": {"sala": "sala-mirante"}}, result["requestState"]
        )
    data = second["result"]["structuredContent"]
    assert second["result"]["resultType"] == "complete"
    assert (data["sala"], data["reservado"], data["responsavel"]) == ("sala-mirante", True, "Marty")


async def test_decline_completes_without_booking_and_without_error():
    async with mcp_client() as client:
        _, first = await book(client, CONFLICT)
        key = next(iter(first["result"]["inputRequests"]))
        _, second = await retry(client, CONFLICT, key, {"action": "decline"}, first["result"]["requestState"])
    result = second["result"]
    assert result["resultType"] == "complete"
    assert not result.get("isError")
    assert result["structuredContent"]["reservado"] is False
    assert result["structuredContent"]["motivo"] == "recusado"


async def test_tampered_request_state_is_rejected():
    async with mcp_client() as client:
        _, first = await book(client, CONFLICT)
        state = first["result"]["requestState"]
        key = next(iter(first["result"]["inputRequests"]))
        tampered = state[:-1] + ("A" if state[-1] != "A" else "B")
        _, second = await retry(
            client, CONFLICT, key, {"action": "accept", "content": {"sala": "sala-fusca"}}, tampered
        )
    assert second["error"]["code"] == -32602


async def test_tampered_arguments_never_take_effect():
    async with mcp_client() as client:
        _, first = await book(client, CONFLICT)
        key = next(iter(first["result"]["inputRequests"]))
        forged = {**CONFLICT, "responsavel": "Biff"}
        _, second = await retry(
            client,
            forged,
            key,
            {"action": "accept", "content": {"sala": "sala-fusca"}},
            first["result"]["requestState"],
        )
    assert second["error"]["code"] == -32602


async def test_choice_outside_the_offered_options_is_refused():
    async with mcp_client() as client:
        _, first = await book(client, CONFLICT)
        key = next(iter(first["result"]["inputRequests"]))
        _, second = await retry(
            client,
            CONFLICT,
            key,
            {"action": "accept", "content": {"sala": "sala-aquario"}},
            first["result"]["requestState"],
        )
    assert second["result"]["isError"] is True


async def test_request_state_survives_a_restart_with_the_same_secret():
    secret = secrets.token_hex(32)
    async with mcp_client(secret) as client:
        _, first = await book(client, CONFLICT)
    key = next(iter(first["result"]["inputRequests"]))
    async with mcp_client(secret) as fresh:  # brand-new app: nothing in memory
        _, second = await retry(
            fresh,
            CONFLICT,
            key,
            {"action": "accept", "content": {"sala": "sala-fusca"}},
            first["result"]["requestState"],
        )
    assert second["result"]["structuredContent"]["sala"] == "sala-fusca"


async def test_request_state_from_another_secret_is_rejected():
    async with mcp_client(secrets.token_hex(32)) as client:
        _, first = await book(client, CONFLICT)
    key = next(iter(first["result"]["inputRequests"]))
    async with mcp_client(secrets.token_hex(32)) as other:
        _, second = await retry(
            other,
            CONFLICT,
            key,
            {"action": "accept", "content": {"sala": "sala-fusca"}},
            first["result"]["requestState"],
        )
    assert second["error"]["code"] == -32602


async def test_conflict_without_elicitation_capability_is_32021():
    async with mcp_client() as client:
        status, body = await book(client, CONFLICT, caps={})
    assert status == 400
    assert body["error"]["code"] == -32021
    assert body["error"]["data"]["requiredCapabilities"] == {"elicitation": {"form": {}}}


async def test_conflict_without_alternatives_is_a_tool_error():
    args = {
        **CONFLICT,
        "sala": "sala-mirante",
        "inicio": "2026-11-03T11:00:00-03:00",
        "fim": "2026-11-03T12:00:00-03:00",
    }
    async with mcp_client() as client:
        await book(client, args)
        _, body = await book(client, args)
    assert body["result"]["isError"] is True
    assert "Sem alternativas disponiveis no intervalo" in body["result"]["content"][0]["text"]


async def test_unknown_tool_is_refused():
    async with mcp_client() as client:
        _, body = await rpc(client, "tools/call", {"name": "voar", "arguments": {}}, "voar")
    assert body.get("error", {}).get("code") == -32602 or body["result"]["isError"] is True


async def test_every_request_is_logged_with_method_id_and_traceparent(caplog):
    caplog.set_level(logging.INFO, logger="mcp_server.requests")
    async with mcp_client() as client:
        _, first = await book(client, CONFLICT)
    record = next(r for r in caplog.records if r.name == "mcp_server.requests")
    assert record.method == "tools/call"
    assert record.id
    assert record.traceparent == TRACEPARENT
    assert record.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    state = first["result"]["requestState"]
    assert all(state not in r.getMessage() and state not in str(vars(r)) for r in caplog.records)


async def test_metrics_expose_exemplars_in_openmetrics():
    async with mcp_client() as client:
        await book(client, CONFLICT)
        response = await client.get("/metrics", headers={"Accept": "application/openmetrics-text"})
    assert "mcp_request_duration_seconds_bucket" in response.text
    assert "trace_id=" in response.text
    assert "mrtr_input_required_total" in response.text
