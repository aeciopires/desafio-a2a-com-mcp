<!-- TOC -->
- [Decisões técnicas](#decisões-técnicas)
  - [Stack](#stack)
  - [Servidor MCP](#servidor-mcp)
  - [Agente](#agente)
  - [Observabilidade (extra)](#observabilidade-extra)
  - [Docker e sistemas operacionais](#docker-e-sistemas-operacionais)
  - [Limitações conhecidas](#limitações-conhecidas)
<!-- TOC -->

# Decisões técnicas

## Stack

| Item | Escolha | Motivo |
|---|---|---|
| Linguagem | Python 3.14.8 (mise) | os exemplos de wire foram capturados com o SDK Python; o enunciado aceita Python ≥ 3.10 |
| SDK MCP | `mcp==2.3.0` (revisão `2026-07-28`) | SDK oficial v2, com MRTR de primeira classe (`Resolve`/`Elicit` → `InputRequiredResult`) e `RequestStateBoundary` |
| Pacotes | `uv` com `uv.lock` por projeto, versões travadas com `==` | build reprodutível; `make install` usa `uv sync --frozen` |
| HTTP | Starlette 1.8 + Uvicorn 0.54 | o SDK MCP já usa Starlette; o agente segue o mesmo stack |
| Versão do projeto | arquivo `VERSION` (`0.1.0`) | fonte única para Python (`serverInfo`, `clientInfo`, Agent Card, `/healthz`), Makefile e tags das imagens |
| LLM | nenhum | requisito: agente determinístico; nenhum SDK de provedor nas dependências |

## Servidor MCP

- **MRTR do jeito do SDK.** `reservar_sala` recebe um parâmetro `escolha` resolvido por `escolha_de_sala`. Esse resolver devolve `None` quando a sala está livre, levanta `ToolError` com a mensagem exata quando há violação de regra ou falta de alternativas, e devolve `Elicit(...)` no conflito. Daí o SDK responde `input_required` sem executar o corpo da tool. No retry, ele casa a resposta com a mesma pergunta (pelo digest dela) e injeta o resultado: `AcceptedElicitation`, `DeclinedElicitation` ou `CancelledElicitation`. A chave do `inputRequests` é atribuída pelo SDK (`mcp_server.server:escolha_de_sala`).
- **Schema da elicitation dinâmico.** `create_model` com `Literal[...alternativas]` gera um schema plano: `enum` com duas ou mais opções, `const` com uma. Uma escolha fora das opções é recusada pelo próprio SDK (`isError`).
- **Proteção do `requestState`:** detalhada em [request-state.md](request-state.md) (AES-256-GCM, TTL de 10 min, vínculo com os argumentos). Para argumentos adulterados no retry, o caminho adotado é **rejeitar** (`-32602`).
- **Rejeições de protocolo** (`_meta` incompleto → `-32602`/400, headers divergentes → `-32020`, capability ausente → `-32021`/400, URI inexistente → `-32602`) vêm do transporte do SDK. O servidor só garante que nada é inferido de requests anteriores: o app é stateless (`stateless_http=True`, `json_response=True`).
- **Log no stderr:** um middleware ASGI lê o corpo uma vez e o reentrega intacto ao SDK. Ele registra `method`, `id`, `traceparent`, `trace_id`, `span_id`, `result_type`, `error_code` e a duração.
- **Persistência** em memória, carregada de `dados/` no boot. `make restore` recria os containers e volta ao estado inicial.

## Agente

- **Cliente MCP próprio, fino, sobre `httpx`, com os tipos do SDK (`mcp_types`).** O `Client` do SDK não serve aqui por dois motivos:
  1. Com um callback de elicitation, ele resolve o `input_required` sozinho, e a Task nunca pausaria.
  2. Quando o callback existe, ele declara `elicitation: {form, url}` ([mcp/client/session.py](https://github.com/modelcontextprotocol/python-sdk), método que monta `ClientCapabilities`), enquanto o enunciado exige exatamente `{"elicitation": {"form": {}}}`.

  O cliente próprio controla o `_meta` completo em cada request, os headers espelhados (`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`) e ids sempre novos (contador monotônico).
- **A2A feito à mão, e não com `a2a-sdk` 1.2.2.** Evidência do spike: sem o header `A2A-Version`, o SDK responde

  ```json
  {"error":{"code":-32009,"message":"A2A version '0.3' is not supported by this handler. Expected version '1.0'."}}
  ```

  e nem os exemplos oficiais (`exemplos/wire/08..10`) nem o validador enviam esse header. O binding JSON-RPC tem dois métodos (`SendMessage`, `GetTask`) e segue o formato v1.0 do wire: `supportedInterfaces`, `TASK_STATE_*`, `ROLE_USER`/`ROLE_AGENT`, `result.task`.
- **Estado das Tasks:** `TaskStore` em memória no agente. Cada Task tem um `asyncio.Lock`, e o estado da ponte (`PendingInput`) fica num campo privado que a serialização (`to_wire`) nunca inclui.
- **Descoberta em runtime:** `tools/list` e `resources/read politica://uso` no início de cada Task. Se `reservar_sala` não for descoberta, a Task falha com mensagem clara.
- **Escolha fora do enum** não chama o MCP. É validação de protocolo contra o schema recebido, não regra de domínio: a Task continua `INPUT_REQUIRED` e repete a mesma linha.

## Observabilidade (extra)

- OpenTelemetry com instrumentação manual. Não usamos auto-instrumentação do `httpx`, para que o único `traceparent` enviado ao MCP seja o do `_meta`.
- Exemplars nos histogramas (OpenMetrics + `exemplar-storage`).
- Logs JSON no stderr, coletados pelo Grafana Alloy (o Promtail está descontinuado) e enviados ao Loki.
- **Jaeger 2.22.0 com o Grafana via `/api/v3`:** a 2.21 removeu `/api/services`, `/api/services/{s}/operations` e a busca `/api/traces` ([jaeger#9260](https://github.com/jaegertracing/jaeger/pull/9260)); `/api/traces/{id}` e `/api/dependencies` continuam. O plugin Jaeger do Grafana (13.0.5, embutido no Grafana 13.2.4) só usa `/api/v3` com o feature toggle `jaegerEnableGrpcEndpoint` (`GF_FEATURE_TOGGLES_ENABLE` no compose), conforme o [troubleshooting do Grafana](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/jaeger/troubleshooting/). Com ele funcionam health check, serviços, operações, trace por id e grafo de dependências. Testado: sem o toggle o health responde `request failed: 404 Not Found`.
- **Limitação conhecida, a busca no Explore:** o plugin ainda chama `/api/traces` para a aba *Search*, mesmo com o toggle (TODO no código do plugin, aguardando [jaeger#7594](https://github.com/jaegertracing/jaeger/issues/7594)). Para buscar traces, use a UI do Jaeger (`:16686`). Os fluxos do projeto usam trace por id (dashboards, exemplars, links do Loki) e não dependem da busca.
- **Atributos de span só string/int:** pelo `/api/v3`, o plugin falha ao ler atributos bool ou double e descarta arrays ([grafana-jaeger-datasource#83](https://github.com/grafana/grafana-jaeger-datasource/issues/83), aberto). Por isso `mcp.retry` e `mcp.is_error` são gravados como `"true"`/`"false"` e `mrtr.alternatives` como texto separado por vírgula. Quando o bug for corrigido, dá para voltar aos tipos nativos.
- **Métricas internas do Jaeger:** o Prometheus coleta `jaeger:8888` (job `jaeger`), que alimenta o dashboard [24836 (Jaeger V2 OpenTelemetry Metrics)](https://grafana.com/grafana/dashboards/24836-jaeger-v2-opentelemetry-metrics/). O JSON original fica intacto em `observability/grafana/vendor/` e o `gen_dashboards.py` o adapta: fixa o datasource `prometheus` e aceita os contadores com ou sem `_total`, porque o Jaeger 2.22 os expõe sem o sufixo (`otelcol_receiver_accepted_spans`).

## Docker e sistemas operacionais

- Imagens `python:3.14.8-slim-trixie` e `ghcr.io/astral-sh/uv:0.13.1`, ambas travadas por digest. Build multi-stage, usuário não root e `HEALTHCHECK` em `/healthz`.
- `make build-multiarch` gera `linux/amd64` e `linux/arm64`. Isso cobre Ubuntu amd64 e macOS Intel/Apple Silicon, porque no macOS os containers rodam numa VM Linux do **Colima** (não usamos Docker Desktop).
- `scripts/check_os.sh` valida Ubuntu 22.04/24.04/26.04 amd64 e macOS amd64/arm64 antes de `install`, `up` e `build`.

## Limitações conhecidas

- A2A sem streaming, push e autenticação (fora de escopo).
- As reservas não sobrevivem a restart (o enunciado não exige). O `requestState` sobrevive.
