"""Plain MCP client script, no A2A: discover, read the policy, book, answer the elicitation by hand.

    PYTHONPATH=agente/src agente/.venv/bin/python -m agent.cli \
        reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty

Useful to watch one MRTR round trip without the Task machinery around it.
"""

from __future__ import annotations

import asyncio
import json
import sys

import mcp_types

from agent.bridge import POLICY_URI, allowed_choices, extract_policy_version
from agent.config import CLIENT_NAME, ConfigError, load_settings
from agent.mcp_host import McpHost, McpRpcError, McpUnavailable
from agent.parser import ParseError, parse_booking


async def run(text: str) -> int:
    settings = load_settings()
    mcp = McpHost(settings.mcp_url, settings.mcp_timeout, settings.version, CLIENT_NAME)
    try:
        request = parse_booking(text)
        tools = [tool.name for tool in await mcp.list_tools()]
        print(f"tools/list -> {tools}")
        version = extract_policy_version(await mcp.read_text_resource(POLICY_URI))
        print(f"politica -> {version}")
        result = await mcp.call_tool("reservar_sala", request.as_arguments())
        while isinstance(result, mcp_types.InputRequiredResult):
            key, elicitation = next(iter((result.input_requests or {}).items()))
            options = allowed_choices(elicitation.params.requested_schema)  # type: ignore[union-attr]
            print(f"input_required ({key}): {elicitation.params.message}")  # type: ignore[union-attr]
            answer = input(f"escolha uma sala {options} ou 'recusar': ").strip()
            response = (
                {"action": "decline"} if answer == "recusar" else {"action": "accept", "content": {"sala": answer}}
            )
            result = await mcp.call_tool(
                "reservar_sala",
                request.as_arguments(),
                input_responses={key: response},
                request_state=result.request_state,
            )
        print(
            json.dumps(result.model_dump(by_alias=True, exclude_none=True, mode="json"), indent=2, ensure_ascii=False)
        )
        return 1 if result.is_error else 0
    except (ParseError, McpRpcError, McpUnavailable) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    finally:
        await mcp.aclose()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(" ".join(sys.argv[1:])))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
