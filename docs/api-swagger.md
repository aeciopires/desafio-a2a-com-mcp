<!-- TOC -->
- [API e Swagger](#api-e-swagger)
  - [Roteiro no Swagger do agente](#roteiro-no-swagger-do-agente)
  - [Roteiro no Swagger do servidor MCP](#roteiro-no-swagger-do-servidor-mcp)
  - [Equivalente com curl](#equivalente-com-curl)
<!-- TOC -->

# API e Swagger

Cada processo serve um documento OpenAPI 3.1 e uma Swagger UI com exemplos prontos para testar no navegador.

| Processo | Swagger UI | OpenAPI |
|---|---|---|
| Agente (A2A) | http://localhost:7300/docs | http://localhost:7300/openapi.json |
| Servidor MCP | http://localhost:7301/docs | http://localhost:7301/openapi.json |

Analogia: o Swagger é o **cardápio com fotos** do restaurante. Você vê os pratos (endpoints), escolhe um exemplo pronto e pede ("Try it out" → "Execute").

As rotas `/docs`, `/openapi.json`, `/metrics` e `/healthz` ficam fora do endpoint MCP: não passam pela validação de `_meta` e não aparecem no log de requests do stderr.

## Roteiro no Swagger do agente

1. Abra http://localhost:7300/docs, `POST /a2a`, **Try it out**.
2. Exemplo **sala-ocupada** → Execute. A Task volta em `TASK_STATE_INPUT_REQUIRED` com `alternativas: sala-fusca, sala-mirante`. Copie o `result.task.id`.
3. Exemplo **escolha**: troque `<taskId devolvido na pausa>` pelo id copiado → Execute → `TASK_STATE_COMPLETED`, com o artifact `reserva`.
4. Exemplo **get-task** com o mesmo id para ver o estado final.

## Roteiro no Swagger do servidor MCP

1. Abra http://localhost:7301/docs, `POST /mcp`, **Try it out**.
2. Os headers `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` precisam espelhar o corpo. Para `tools/call`, use `Mcp-Method: tools/call` e `Mcp-Name: reservar_sala`; para `resources/read`, `Mcp-Name: politica://uso`; para `tools/list`, deixe `Mcp-Name` vazio. Um header divergente devolve `-32020`.
3. Exemplo **reservar-conflito** → `input_required`. Copie a chave de `inputRequests` e o `requestState`.
4. Exemplo **reservar-retry**: cole a chave e o `requestState` → `complete`.

## Equivalente com curl

```bash
# Agent Card
curl -s http://localhost:7300/.well-known/agent-card.json

# Pausa (corpo do exemplo oficial)
python3 -c "import json;print(json.dumps(json.load(open('exemplos/wire/08-a2a-send-message.json'))['request']['body']))" \
  | curl -s http://localhost:7300/a2a -H 'Content-Type: application/json' \
         -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' -d @-

# Continuação (troque TASK_ID)
curl -s http://localhost:7300/a2a -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":2,"method":"SendMessage",
  "params":{"message":{"messageId":"m2","role":"ROLE_USER","parts":[{"text":"escolha=sala-mirante"}],"taskId":"TASK_ID"}}}'

# MCP direto: conflito -> input_required
python3 -c "import json;print(json.dumps(json.load(open('exemplos/wire/03-tools-call-conflito-input-required.json'))['request']['body']))" \
  | curl -s http://localhost:7301/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
         -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/call' -H 'Mcp-Name: reservar_sala' -d @-
```

Para ver uma rodada MRTR sem A2A no meio, há também um cliente de linha de comando:

```bash
set -a; source .env; set +a
cd agente && PYTHONPATH=src mise exec -- uv run python -m agent.cli \
  reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty
```
