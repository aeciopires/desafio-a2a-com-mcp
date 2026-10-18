<!-- TOC -->
- [Plano de implementação: A Ponte (A2A com MCP)](#plano-de-implementação-a-ponte-a2a-com-mcp)
  - [1. Objetivo e escopo](#1-objetivo-e-escopo)
  - [2. Decisões de arquitetura](#2-decisões-de-arquitetura)
  - [3. Estrutura do repositório](#3-estrutura-do-repositório)
  - [4. Fase 0: preparação e spike dos SDKs](#4-fase-0-preparação-e-spike-dos-sdks)
  - [5. Fase 1: servidor MCP](#5-fase-1-servidor-mcp)
  - [6. Fase 2: MRTR na reserva](#6-fase-2-mrtr-na-reserva)
  - [7. Fase 3: agente como host MCP](#7-fase-3-agente-como-host-mcp)
  - [8. Fase 4: agente como servidor A2A](#8-fase-4-agente-como-servidor-a2a)
  - [9. Fase 5: a ponte](#9-fase-5-a-ponte)
  - [10. Fase 6: OpenAPI e Swagger](#10-fase-6-openapi-e-swagger)
  - [11. Fase 7: observabilidade com Prometheus, Grafana, Jaeger e Loki](#11-fase-7-observabilidade-com-prometheus-grafana-jaeger-e-loki)
    - [11.1 Métricas e dashboards](#111-métricas-e-dashboards)
    - [11.2 Traces com OpenTelemetry e Jaeger](#112-traces-com-opentelemetry-e-jaeger)
    - [11.3 Logs com Grafana Loki e Grafana Alloy](#113-logs-com-grafana-loki-e-grafana-alloy)
    - [11.4 Correlação de métricas, traces e logs no Grafana](#114-correlação-de-métricas-traces-e-logs-no-grafana)
  - [12. Fase 8: versão, Docker e sistemas operacionais](#12-fase-8-versão-docker-e-sistemas-operacionais)
  - [13. Fase 9: Makefile e mise](#13-fase-9-makefile-e-mise)
  - [14. Fase 10: testes](#14-fase-10-testes)
  - [15. Fase 11: documentação](#15-fase-11-documentação)
  - [16. Fase 12: CLAUDE.md](#16-fase-12-claudemd)
  - [17. Variáveis de ambiente](#17-variáveis-de-ambiente)
  - [18. Rastreabilidade das 36 verificações](#18-rastreabilidade-das-36-verificações)
  - [19. Riscos e pontos em aberto](#19-riscos-e-pontos-em-aberto)
  - [20. Checklist final de entrega](#20-checklist-final-de-entrega)
<!-- TOC -->

# Plano de implementação: A Ponte (A2A com MCP)

Plano derivado de [TASK.md](TASK.md), de [exemplos/wire/](exemplos/wire/) e de [validador/validar.py](validador/validar.py). Documentação em pt-BR; código, identificadores e comentários em en-US. Os nomes que fazem parte do contrato (tools, campos JSON, mensagens de erro, skill `reservar-sala`) ficam exatamente como o enunciado define.

## 1. Objetivo e escopo

Entregar dois processos independentes, que se comunicam por HTTP:

| Processo | Porta padrão | Endpoints | Papel |
|---|---|---|---|
| `servidor-mcp` | `7301` (`MCP_PORT`) | `POST /mcp`, `GET /metrics`, `GET /healthz`, `GET /docs`, `GET /openapi.json` | Servidor MCP Streamable HTTP stateless: 3 tools, 1 resource, MRTR |
| `agente` | `7300` (`AGENT_PORT`) | `GET /.well-known/agent-card.json`, `POST /a2a`, `GET /metrics`, `GET /healthz`, `GET /docs`, `GET /openapi.json` | Host MCP por dentro, servidor A2A v1.0 (JSON-RPC) por fora |

Além disso, conforme os pedidos adicionais do TASK.md: Docker Compose (com Prometheus, Grafana, Jaeger, Loki e Alloy, correlacionando métricas, traces e logs), Makefile, mise, arquivo `VERSION` (`0.1.0`), checagem de SO suportado, Swagger, testes unitários e de integração, documentação em `docs/` com diagramas Mermaid e analogias, `CLAUDE.md`, `CONTRIBUTING.md`, `REQUIREMENTS*.md` e script de TOC.

Fora de escopo (do enunciado): auth, streaming/SSE/push, `referenceTaskIds`, card estendido/JWS, prompts/subscriptions/progress, persistência de reservas em disco, UI.

Sobre OpenTelemetry: o enunciado não exige spans, só a propagação do `traceparent` e o registro dele em log. Os spans exportados para o Jaeger entram como **extra opcional de observabilidade**. Eles não substituem o log do `traceparent` no stderr, não mudam o wire dos protocolos e não podem quebrar nada se o Jaeger estiver fora do ar.

**Proibido alterar:** `dados/`, `validador/` (inclusive `validador/README.md`) e `exemplos/`.

## 2. Decisões de arquitetura

> **Ajustes feitos durante a implementação** (resultado do spike da Fase 0, detalhados em [docs/decisoes-tecnicas.md](docs/decisoes-tecnicas.md)):
>
> - `mcp==2.3.0` sela o `requestState` com **AES-256-GCM** (AEAD), não com HMAC, e o vincula ao digest dos argumentos. Argumentos adulterados no retry são **rejeitados** com `-32602`.
> - **`a2a-sdk` 1.2.2 não foi usado**: sem o header `A2A-Version`, ele trata o request como A2A 0.3 e responde `-32009`. O binding JSON-RPC v1.0 foi feito à mão em Starlette.
> - **Cliente MCP do agente**: cliente fino com `httpx` e tipos `mcp_types`. O `Client` do SDK resolve o `input_required` sozinho e declara `elicitation: {form, url}`.
> - **Jaeger 2.22.0**: a 2.21+ removeu `/api/services` e a busca `/api/traces`. O Grafana lê o Jaeger via `/api/v3` com o feature toggle `jaegerEnableGrpcEndpoint`; a busca do Explore não funciona (limitação do plugin) e os atributos de span são só string/int (grafana-jaeger-datasource#83).
> - **Testes de integração** num projeto uv da raiz, que tem só `[dependency-groups]`. O ruff da raiz exclui `dados/`, `validador/` e `exemplos/`, e há `make check-protected`.
> - `MCP_HOST`/`AGENT_HOST` têm padrão `127.0.0.1` fora do Docker, o que liga a proteção contra DNS rebinding do SDK, e `0.0.0.0` dentro dos containers.

1. **Linguagem: Python 3.14** (via mise; `requires-python = ">=3.14,<3.15"` nos `pyproject.toml`), SDK oficial `mcp` v2 (revisão `2026-07-28`). Os exemplos de wire foram capturados com o SDK Python, então os formatos (chave `module:resolver`, `outputSchema` do pydantic, `requestState` `v1.…`) saem naturalmente.
2. **Gerenciador de pacotes: `uv`**, um `pyproject.toml` + `uv.lock` por processo, com versões travadas (`==`). Nenhum SDK de provedor de LLM nas dependências.
3. **Servidor MCP**: o transporte Streamable HTTP stateless do SDK, montado numa app ASGI (Starlette) que também expõe `/metrics`, `/healthz`, `/docs` e `/openapi.json` em rotas separadas, sem passar pela validação de `_meta`.
4. **MRTR no servidor**: usar a API de primeira classe do SDK (`input_required` / resolver de elicitation) e o utilitário de selagem de `requestState` do próprio SDK (AEAD AES-256-GCM, conforme verificado no spike), com a chave em `REQUEST_STATE_SECRET`. Nada fica guardado em memória entre o `input_required` e o retry.
5. **Cliente MCP no agente**: o agente precisa ver o `input_required` cru. Preferência: o cliente do SDK **sem** callback de elicitation, desde que ele devolva o resultado `input_required` em vez de resolvê-lo. Alternativa (se o spike mostrar que o SDK sempre resolve sozinho ou não deixa controlar o id/headers): um cliente JSON-RPC fino com `httpx`, documentado no README com a evidência. Em ambos os casos o cliente é um objeto vivo reutilizado, e cada request carrega `_meta` completo (sem sessão).
6. **A2A**: avaliar `a2a-sdk` (Python) com suporte à v1.0 (enum `TASK_STATE_*`, `supportedInterfaces`, métodos `SendMessage`/`GetTask`). Se a versão disponível não produzir o formato exato de `exemplos/wire/07..10`, implementar o binding JSON-RPC à mão em Starlette (é pequeno: 2 métodos + card). A decisão sai do spike da Fase 0.
7. **Estado das Tasks**: `TaskStore` em memória no agente (dict protegido por `asyncio.Lock` por task). O `requestState` e a chave do `inputRequests` ficam num campo privado da Task (`_pending_mrtr`), nunca serializado.
8. **Persistência de reservas**: em memória no servidor MCP, carregada de `dados/reservas.json` no boot; `dados/` montado como somente leitura no container. `make restore` = reiniciar os processos (estado inicial).
9. **Versão**: arquivo `VERSION` na raiz é a fonte única (`0.1.0`), lida pelo Python (`__version__`, `serverInfo`, `clientInfo`, Agent Card `version`), pelo Makefile e pelas tags das imagens Docker.
10. **Tracing**: OpenTelemetry SDK nos dois processos, com propagador W3C Trace Context e exportação OTLP/HTTP para o **Jaeger v2** (`jaegertracing/jaeger`, imagem all-in-one multi-arch; a linha v1 `all-in-one` está descontinuada). O `traceparent` que o agente coloca no `_meta` passa a ser gerado a partir do span OTel corrente: mesmo trace-id do cliente A2A, span-id do span de cliente MCP. O servidor MCP extrai o contexto do `_meta.traceparent`, que é o canal que a spec reserva. Exportação em `BatchSpanProcessor`, fora do caminho da resposta.
11. **Logs centralizados**: os dois processos continuam escrevendo JSON por linha no stderr, como o enunciado exige, agora com `trace_id` e `span_id` em cada linha. O **Grafana Alloy** coleta os logs dos containers pelo socket do Docker e os envia ao **Grafana Loki**. Não usamos Promtail, que está descontinuado, nem o logging driver do Loki, que exige plugin instalado no host e complica o uso com Colima. O Grafana é provisionado com os três datasources (Prometheus, Jaeger e Loki), com UIDs fixos e links cruzados entre eles.

## 3. Estrutura do repositório

```
.
├── VERSION                         # 0.1.0, fonte única de versão
├── Makefile
├── mise.toml                       # python, uv (docker vem do SO)
├── docker-compose.yml              # mcp-server, agent, prometheus, grafana, jaeger, loki, alloy
├── .env.example                    # nomes das variáveis, sem valores
├── .gitignore                      # + .env, .venv, caches, cobertura
├── README.md                       # pt-BR, 4 seções obrigatórias + links para docs/
├── CLAUDE.md
├── CONTRIBUTING.md
├── REQUIREMENTS.md                 # genérico, redireciona por SO
├── REQUIREMENTS-UBUNTU.md
├── REQUIREMENTS-MACOS.md
├── PLAN.md
├── scripts/
│   ├── check_os.sh                 # usado pelo Makefile
│   ├── check_ports.sh
│   ├── gen_secret.sh               # grava REQUEST_STATE_SECRET no .env se vazio
│   └── toc.py                      # TOC idempotente
├── docs/                           # pt-BR, Mermaid + analogias
├── observability/
│   ├── prometheus/prometheus.yml
│   ├── loki/loki.yaml              # single-binary, filesystem, retenção curta
│   ├── alloy/config.alloy          # docker discovery -> parse JSON -> Loki
│   └── grafana/
│       ├── provisioning/datasources/datasources.yaml   # Prometheus, Jaeger, Loki (UIDs fixos + correlações)
│       ├── provisioning/dashboards/dashboards.yaml
│       └── dashboards/*.json
├── servidor-mcp/
│   ├── Dockerfile
│   ├── pyproject.toml / uv.lock
│   ├── src/mcp_server/
│   │   ├── __main__.py             # entrypoint, valida env, sobe uvicorn
│   │   ├── app.py                  # ASGI: /mcp + rotas auxiliares
│   │   ├── config.py               # env vars, VERSION, validação do secret
│   │   ├── domain.py               # Room, Reservation, policy, alternatives
│   │   ├── repository.py           # store em memória
│   │   ├── tools.py                # listar_salas, consultar_disponibilidade, reservar_sala
│   │   ├── resources.py            # politica://uso
│   │   ├── logging_mw.py           # log stderr: method, id, traceparent
│   │   ├── telemetry.py            # setup OTel, extração do _meta.traceparent
│   │   ├── metrics.py
│   │   └── openapi.py
│   └── tests/{unit,integration}/
└── agente/
    ├── Dockerfile
    ├── pyproject.toml / uv.lock
    ├── src/agent/
    │   ├── __main__.py
    │   ├── app.py                  # card + /a2a + rotas auxiliares
    │   ├── config.py
    │   ├── card.py                 # Agent Card v1.0
    │   ├── a2a_rpc.py              # SendMessage, GetTask, erros JSON-RPC
    │   ├── tasks.py                # Task, TaskStore, máquina de estados
    │   ├── parser.py               # "reservar ..." e "escolha=..."
    │   ├── mcp_host.py             # cliente MCP: discovery, _meta, headers, ids
    │   ├── bridge.py               # A PONTE: input_required <-> INPUT_REQUIRED
    │   ├── tracing.py              # traceparent: parse, contexto por Task
    │   ├── telemetry.py            # setup OTel (provider, exporter OTLP, resource)
    │   ├── metrics.py
    │   └── openapi.py
    └── tests/{unit,integration}/
```

Testes de integração de ponta a ponta (que exercitam os dois processos) ficam em `tests/integration/` na raiz.

## 4. Fase 0: preparação e spike dos SDKs

1. Criar `VERSION`, `mise.toml`, `.env.example`, ajustar `.gitignore`.
2. Descobrir no PyPI a versão estável mais recente do `mcp` v2 que implementa `2026-07-28` e do `a2a-sdk` com A2A v1.0; travar com `==`.
3. Spike do SDK MCP (lendo as docstrings, como o TASK sugere): `grep -rn "input_required\|InputRequired\|request_state\|requestState" .venv/lib/*/site-packages/mcp` para achar:
   - como uma tool devolve `input_required` com elicitation em form mode (resolver nomeado → chave `module:name`);
   - o utilitário de selagem do `requestState` (HMAC/AEAD, expiração) e como passar o segredo;
   - se o SDK já valida `_meta` obrigatório (`-32602`/HTTP 400), capability de elicitation (`-32021`) e espelhamento de headers (`-32020`);
   - como o cliente do SDK se comporta sem callback de elicitation.
4. Spike do `a2a-sdk`: confirmar o formato do card (`supportedInterfaces[].protocolBinding = "JSONRPC"`), os nomes de método `SendMessage`/`GetTask`, a forma `result.task` e o enum `TASK_STATE_*`. Comparar contra `exemplos/wire/07..10`.
5. Registrar as decisões (SDK ou implementação fina) em `docs/decisoes-tecnicas.md`. Se houver limitação real do SDK, documentar no README com o trecho da evidência, sem reescrever o protocolo.

**Saída:** dependências travadas e um esqueleto que sobe nas duas portas.

## 5. Fase 1: servidor MCP

1. **Config** (`config.py`): `MCP_HOST`, `MCP_PORT=7301`, `MCP_PATH=/mcp`, `DATA_DIR`, `REQUEST_STATE_SECRET`, `REQUEST_STATE_TTL_SECONDS` (padrão 600, validado entre 300 e 1800). No boot, falhar com mensagem clara se o secret faltar ou tiver menos de 32 bytes (`REQUEST_STATE_SECRET must be at least 32 bytes (64 hex chars). Generate one with: make secret`).
2. **Domínio** (`domain.py`, funções puras e testáveis):
   - parse ISO 8601 com offset; a política é avaliada em `-03:00` fixo;
   - ordem de validação: sala existe → `fim > inicio` → janela 08:00–20:00 (início e fim) → duração ≤ 2h;
   - mensagens exatas como constantes:
     - `Sala inexistente: <id>`
     - `Intervalo invalido: fim deve ser posterior a inicio`
     - `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`
     - `Duracao acima do limite: a politica permite no maximo 2 horas`
     - `Sem alternativas disponiveis no intervalo`
   - sobreposição: `a.inicio < b.fim and b.inicio < a.fim`;
   - alternativas: salas livres no intervalo, `capacidade >= capacidade da pedida`, excluindo a pedida, ordenadas por `(capacidade, id)`, no máximo 3.
3. **Repositório** em memória: carrega salas e reservas; ids sequenciais `res-NNNN` a partir do maior existente.
4. **Tools** com `inputSchema`/`outputSchema` via pydantic (iguais aos de `01-tools-list.json`):
   - `listar_salas` → `{"salas": [...]}` em `structuredContent` + mesmo JSON em bloco de texto;
   - `consultar_disponibilidade(sala, inicio, fim)` → `{sala, livre, conflitos[]}`, com as mesmas validações;
   - `reservar_sala(sala, inicio, fim, responsavel)` → caminho feliz cria a reserva e devolve `{reserva, reservado, sala, inicio, fim, responsavel, politica, motivo}`.
   - Erros de execução: `isError: true` dentro de `complete`, com a mensagem exata no texto.
5. **Resource** `politica://uso` (`text/markdown`) lendo `dados/politica-de-uso.md`; a versão é extraída da primeira linha (`versao: 2026-11-01`) e usada no campo `politica`. URI inexistente → `-32602` (nunca `contents` vazio).
6. **Capabilities** `tools` e `resources`. `serverInfo` = `central-de-salas` / versão do `VERSION`.
7. **Log no stderr** (middleware ASGI que lê o corpo JSON-RPC sem consumi-lo): uma linha JSON por request com `ts`, `level`, `service`, `method`, `id`, `name` (tool/URI), `traceparent`, `trace_id`, `span_id`, `http_status`, `duration_ms`. `trace_id`/`span_id` vêm do span corrente ou, com o OTel desligado, do próprio `traceparent`; são eles que o Loki usa para a correlação com o Jaeger (11.4). Nunca loga o `requestState` inteiro (só um hash curto). O mesmo middleware extrai o contexto W3C do `_meta.traceparent` e abre o span de servidor do request (Fase 7).
8. **Rejeições de protocolo**: `_meta` sem `protocolVersion` ou `clientCapabilities` → `-32602` + HTTP 400; header divergente do corpo → `-32020`; tool inexistente → `-32602` ou `isError`. Se o SDK não fizer alguma delas, implementar num middleware.

## 6. Fase 2: MRTR na reserva

1. No conflito, calcular as alternativas. Nenhuma → `isError` com `Sem alternativas disponiveis no intervalo`.
2. Com alternativas: devolver `resultType: input_required` com **uma** entrada em `inputRequests`, `elicitation/create` em `mode: form`, `requestedSchema` plano `{sala: {type: string, enum: [...]}}` (o `const` com uma alternativa só também é aceito), mensagem `A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.`
3. `requestState` selado pelo `RequestStateBoundary` do SDK (AES-256-GCM com chave derivada de `REQUEST_STATE_SECRET` por HKDF), contendo: método, tool, digest dos argumentos originais, perguntas feitas, `exp` (TTL padrão 10 min). O conteúdo pode ser legível; não pode ser adulterável.
4. **Capability**: antes de emitir a elicitation, checar `clientCapabilities.elicitation.form` no `_meta` **deste** request. Ausente → `-32021` com `data.requiredCapabilities: {"elicitation": {"form": {}}}` e HTTP 400.
5. **Retry** (`params.inputResponses` + `params.requestState`):
   - verificar a integridade e a expiração; falhou → `-32602`;
   - reconstruir o pedido **a partir do estado selado** (argumentos reenviados são ignorados; verificação 18);
   - `accept` → validar que `content.sala` pertence às alternativas seladas, revalidar a disponibilidade da sala escolhida (se alguém a ocupou entretanto, recalcular e devolver novo `input_required`) e criar a reserva;
   - `decline`/`cancel` → `complete`, sem `isError`, `reservado: false`, `motivo: "recusado"`.
6. Funcionar após restart: como nada fica em memória, basta o mesmo secret (vem do `.env`, estável entre restarts).

## 7. Fase 3: agente como host MCP

1. Começar como **script cliente puro** (`python -m agent.cli`), como sugere o TASK: `tools/list` → `resources/read politica://uso` → `tools/call reservar_sala` → resposta manual à elicitation → retry.
2. `mcp_host.py`:
   - todo request leva `_meta` com `protocolVersion`, `clientInfo` (`agente-central-de-salas`, VERSION), `clientCapabilities: {"elicitation": {"form": {}}}` e `traceparent`;
   - headers `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` (nome da tool ou URI), espelhando o corpo;
   - ids JSON-RPC por contador global monotônico → o retry sempre tem id novo;
   - `tools/list` antes da primeira chamada (descoberta em runtime e cache das tools descobertas; se a tool `reservar_sala` não for descoberta, a Task falha com mensagem clara);
   - leitura de `politica://uso` e extração da versão da primeira linha.
3. `tracing.py`: extrai o contexto do header `traceparent` do request A2A com o propagador W3C do OpenTelemetry. Cada request MCP roda num span de cliente filho dele, e o `traceparent` do `_meta` é injetado a partir desse span: mesmo trace-id, span-id novo. Sem header → trace novo. O contexto da Task fica guardado nela e é reutilizado na continuação quando ela chega sem header (as verificações 29 e 32 do validador mandam continuação sem `traceparent`). Com o OTel desligado (`OTEL_SDK_DISABLED=true`), o mesmo módulo gera o `traceparent` à mão, então a propagação nunca depende do Jaeger.
4. Erros: `isError: true` → Task `TASK_STATE_FAILED` com o texto exato da tool na mensagem de status (e no histórico). Falha de rede → `FAILED` com `MCP server unreachable at <url>: <causa>` e log no stderr.
5. Logs do agente no mesmo formato JSON por linha do servidor MCP (`ts`, `level`, `service`, `event`, `task_id`, `context_id`, `task_state`, `mcp_method`, `mcp_request_id`, `trace_id`, `span_id`), um evento por transição de estado da Task e por chamada MCP. Nunca registra o `requestState`.

## 8. Fase 4: agente como servidor A2A

1. **Agent Card** em `/.well-known/agent-card.json`, fiel a `07-a2a-agent-card.json`: `supportedInterfaces[{url: AGENT_PUBLIC_URL, protocolBinding: "JSONRPC", protocolVersion: "1.0"}]`, `capabilities` com streaming/push/extended falsos, skill `reservar-sala`, `version` vinda do `VERSION`.
2. **JSON-RPC em `/a2a`**: `SendMessage` e `GetTask`; método desconhecido → `-32601`; Task inexistente → erro A2A `TaskNotFound`; Task terminal → erro (`UnsupportedOperation`/`InvalidParams`, conforme o SDK).
3. **Máquina de estados** (`tasks.py`): `SUBMITTED → WORKING → {COMPLETED | FAILED | CANCELED | INPUT_REQUIRED}`; `INPUT_REQUIRED → WORKING`; estados terminais são definitivos. Transições inválidas lançam exceção (coberta por teste unitário).
4. `SendMessage` sem `taskId` cria Task com `id` (`task-<hex>`) e `contextId` (`ctx-<hex>`) próprios; histórico com as mensagens do usuário e do agente; `GetTask` devolve o estado corrente e os artifacts.
5. **Artifact** `reserva` com o JSON `{reserva, sala, inicio, fim, responsavel, politica}`; mensagem de status `Reserva <id> confirmada na <sala>.`
6. **Parser** determinístico: `reservar sala=<id> inicio=<iso> fim=<iso> responsavel=<nome>` e `escolha=<id|recusar>`. Pedido mal formado → `FAILED` com mensagem explicando o formato esperado. O agente **não** aplica regra de sala.

## 9. Fase 5: a ponte

Ponto central da avaliação, isolado em `agente/src/agent/bridge.py`:

1. `input_required` do MCP → Task em `TASK_STATE_INPUT_REQUIRED`, mensagem exatamente `alternativas: <id1>, <id2>` (ordem do `enum`, ou `[const]`), sem prefixo.
2. Guardar na Task (campo privado, nunca serializado): `tool`, `arguments`, `input_key`, `request_state`, `allowed` (o enum), `trace_id`.
3. Continuação com `escolha=<valor>`:
   - valor fora de `allowed` (e diferente de `recusar`) → continua `INPUT_REQUIRED` e repete a mesma linha de alternativas, sem chamar o MCP (é validação de protocolo contra o schema recebido, não regra de domínio);
   - `escolha=recusar` → retry com `{"action": "decline"}` → Task `TASK_STATE_CANCELED`;
   - escolha válida → retry `tools/call` com **id novo**, mesmos `arguments`, `inputResponses: {<input_key>: {"action": "accept", "content": {"sala": <valor>}}}` e `requestState` ecoado byte a byte → `COMPLETED` com artifact; se vier um novo `input_required`, pausar de novo; se vier `isError`, `FAILED`.
4. Lock por Task para que duas continuações simultâneas da mesma Task não disputem o estado; Tasks diferentes não compartilham nada (verificação 33).
5. Teste de não vazamento: serializador da Task com allowlist de campos e teste que procura o `requestState` em todas as respostas A2A (verificação 34).

## 10. Fase 6: OpenAPI e Swagger

Em cada processo, `GET /openapi.json` (OpenAPI 3.1, escrito à mão em `openapi.py`, versão do `VERSION`) e `GET /docs` (Swagger UI carregada do jsDelivr com versão travada de `swagger-ui-dist`):

- **Agente**: `GET /.well-known/agent-card.json`, `POST /a2a` com exemplos prontos (`SendMessage` livre, `SendMessage` com conflito, continuação `escolha=...`, `escolha=recusar`, `GetTask`) e o header opcional `traceparent`.
- **Servidor MCP**: `POST /mcp` com os headers `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` como parâmetros, e exemplos copiados de `exemplos/wire/01..06,11` (o retry pede para colar o `requestState` recebido).
- As rotas `/docs`, `/openapi.json`, `/metrics` e `/healthz` não passam pela validação de `_meta` e não aparecem no log de requests MCP.
- Documentar o uso em `docs/api-swagger.md`.

## 11. Fase 7: observabilidade com Prometheus, Grafana, Jaeger e Loki

### 11.1 Métricas e dashboards

Métricas com `prometheus-client`, expostas em `/metrics` nos dois processos. Não há LLM, então as métricas de "chamadas ao modelo" viram métricas de chamadas MCP.

| Origem | Métrica | Tipo / labels |
|---|---|---|
| MCP | `mcp_requests_total` | counter: `method`, `name`, `result_type`, `outcome` |
| MCP | `mcp_request_duration_seconds` | histogram: `method`, `name` |
| MCP | `mcp_protocol_errors_total` | counter: `code` (-32602, -32021, -32020) |
| MCP | `mcp_tool_errors_total` | counter: `tool`, `reason` (sala_inexistente, janela, duracao, intervalo, sem_alternativas) |
| MCP | `reservations_created_total` | counter: `room`, `responsible`, `date` |
| MCP | `reservations_active` | gauge: `room` |
| MCP | `mrtr_input_required_total`, `mrtr_retries_total` | counter: `action` (accept/decline/cancel) |
| MCP | `request_state_rejected_total` | counter: `reason` (tampered, expired, mismatch) |
| Agente | `a2a_requests_total`, `a2a_request_duration_seconds` | `method`, `outcome` |
| Agente | `a2a_tasks_total` | counter: `final_state` |
| Agente | `a2a_tasks_by_state` | gauge: `state` (inclui as confirmações pendentes em `INPUT_REQUIRED`) |
| Agente | `agent_mcp_calls_total`, `agent_mcp_call_duration_seconds` | `method`, `name`, `result_type` |

Os histogramas de duração (`*_duration_seconds`) são registrados com **exemplars** `{trace_id: ...}` do span corrente. Para isso, `/metrics` responde no formato OpenMetrics quando o Prometheus pede (`Accept: application/openmetrics-text`), e o Prometheus roda com `--enable-feature=exemplar-storage`.

Dashboards provisionados (`observability/grafana/dashboards/`):

1. **Negócio**: reservas por sala, por responsável, por data; dia com mais reservas (`topk`); taxa de conflitos; aceites x recusas; ocupação por sala.
2. **Agente/A2A**: Tasks por estado, pausas pendentes, latência p50/p95 com exemplars (clique → trace no Jaeger), taxa de falhas, chamadas MCP por Task e painel de logs do agente (Loki).
3. **MCP/Protocolo**: requests por método, erros por código, `requestState` rejeitados, latência por tool com exemplars e painel de logs do servidor MCP filtrável por `method` e `trace_id`.
4. **Correlação** (variável `trace_id`): logs dos dois serviços no Loki para aquele trace, o trace no Jaeger (painel de traces) e as métricas do mesmo intervalo. Serve para seguir o trace-id impresso pelo validador de ponta a ponta.

Prometheus e Grafana sobem no mesmo compose, com portas configuráveis (`PROMETHEUS_PORT`, `GRAFANA_PORT`) e credenciais do admin do Grafana vindas do `.env`.

### 11.2 Traces com OpenTelemetry e Jaeger

**Container**: serviço `jaeger` no compose, imagem `jaegertracing/jaeger:2.22.0` com digest (Jaeger v2, all-in-one com armazenamento em memória; o Grafana o lê via `/api/v3` com o toggle `jaegerEnableGrpcEndpoint`, e o Prometheus coleta as métricas internas em `jaeger:8888`), UI em `JAEGER_UI_PORT` (padrão `16686`) e receptor OTLP/HTTP em `4318`. O OTLP fica só na rede interna do compose; ele é publicado no host (`JAEGER_OTLP_HTTP_PORT`, padrão `4318`) apenas para quem roda `make run-mcp`/`make run-agent` fora do Docker. Tem healthcheck, e `mcp-server` e `agent` **não** dependem dele para subir.

**Dependências** (travadas com `==` nos dois `pyproject.toml`): `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`. Instrumentação manual dos spans de domínio; não usar auto-instrumentação do `httpx`, para que o único `traceparent` emitido para o MCP seja o do `_meta`, controlado pelo agente.

**Configuração** (`telemetry.py` nos dois processos): `Resource` com `service.name` (`agent` ou `mcp-server`) e `service.version` lido do `VERSION`; sampler `parentbased_always_on`; `BatchSpanProcessor` + exporter OTLP/HTTP. Sem `OTEL_EXPORTER_OTLP_ENDPOINT` ou com `OTEL_SDK_DISABLED=true`, nenhum exporter é registrado. Falha de exportação gera um único aviso no stderr (`OTLP export to <endpoint> failed: <cause>. Traces are disabled until Jaeger is reachable; requests are not affected.`) e não afeta as respostas.

**Spans**:

| Processo | Span | Tipo | Atributos principais |
|---|---|---|---|
| Agente | `a2a SendMessage` / `a2a GetTask` | server | `a2a.method`, `a2a.task_id`, `a2a.context_id`, `a2a.task_state` (final do request) |
| Agente | `bridge.pause` / `bridge.resume` | internal | `a2a.task_id`, `mrtr.alternatives_count`, `mrtr.action` |
| Agente | `mcp tools/list`, `mcp resources/read`, `mcp tools/call reservar_sala` | client | `rpc.system=jsonrpc`, `rpc.jsonrpc.request_id`, `mcp.method`, `mcp.name`, `mcp.result_type`, `mcp.is_error`, `mcp.retry` (`"true"`/`"false"`, string por causa do Grafana) |
| MCP | `mcp <method> [<name>]` | server | `rpc.jsonrpc.request_id`, `mcp.method`, `mcp.name`, `mcp.result_type`, `rpc.jsonrpc.error_code` |
| MCP | `domain.validate`, `domain.alternatives`, `request_state.seal` / `request_state.verify` | internal | `room.id`, `mrtr.alternatives`, `request_state.valid`, `request_state.reject_reason` |

O resultado no Jaeger é um único trace por pedido, com o trace-id que o cliente A2A enviou: o `SendMessage` inicial, as chamadas MCP, a pausa e, na continuação, o retry com id JSON-RPC diferente. O retry aparece ligado ao mesmo trace graças ao contexto guardado na Task.

**Regras**: nunca colocar o `requestState`, nem um pedaço dele, em atributo ou evento de span (apenas `request_state.sha256_8`); nenhum dado de spans entra nas respostas A2A ou MCP. O Jaeger também é datasource do Grafana (11.4), então os traces podem ser vistos tanto na UI do Jaeger quanto no Explore e nos dashboards do Grafana.

### 11.3 Logs com Grafana Loki e Grafana Alloy

**Containers**:

- `loki`: imagem `grafana/loki:<versão 3.x travada>` em modo single-binary, com `observability/loki/loki.yaml` (armazenamento `filesystem` num volume nomeado, schema `v13`/TSDB, `allow_structured_metadata: true`, retenção curta, ex.: 72h). API em `LOKI_PORT` (padrão `3100`) e healthcheck em `/ready`.
- `alloy`: imagem `grafana/alloy:<versão travada>` com `observability/alloy/config.alloy`, montando `/var/run/docker.sock` somente leitura. No macOS o socket é o da VM do Colima, que é o mesmo que o compose usa, então não precisa de configuração extra. UI de debug em `ALLOY_UI_PORT` (padrão `12345`).

**Pipeline do Alloy**:

1. `discovery.docker` limitado aos containers deste projeto compose (filtro pelo label `com.docker.compose.project`);
2. `discovery.relabel` → labels de baixa cardinalidade: `service` (nome do serviço no compose), `container`, `stream` (stdout/stderr);
3. `loki.source.docker` lê stdout e stderr;
4. `loki.process`: `stage.json` extrai `level`, `trace_id`, `span_id`, `method`, `task_id`; `level` vira label; `trace_id`, `span_id`, `task_id` e `method` vão como **structured metadata** (alta cardinalidade, fora dos labels); linhas que não são JSON (logs do Prometheus, Grafana ou Jaeger) passam sem parse;
5. `loki.write` → `http://loki:3100/loki/api/v1/push`.

**Exemplos de LogQL** (documentados em `docs/observabilidade.md`):

- `{service="mcp-server"} | json | method="tools/call"`: todos os `tools/call` no stderr do MCP;
- `{service=~"agent|mcp-server"} | trace_id="<trace-id do validador>"`: o pedido de ponta a ponta nos dois processos;
- `sum by (level) (count_over_time({service="agent"}[5m]))`: volume de logs por nível.

**Resiliência**: o stderr dos containers continua sendo a fonte primária e é o que o avaliador lê com `make logs-mcp`. Se o Loki ou o Alloy estiverem fora do ar, os serviços não percebem.

### 11.4 Correlação de métricas, traces e logs no Grafana

Provisionamento em `observability/grafana/provisioning/datasources/datasources.yaml`, com UIDs fixos (`prometheus`, `jaeger`, `loki`) para que as referências cruzadas e os dashboards versionados não quebrem:

| De → Para | Como |
|---|---|
| Métrica → trace | Prometheus datasource com `exemplarTraceIdDestinations: [{name: trace_id, datasourceUid: jaeger}]`: o ponto de exemplar no gráfico de latência abre o trace no Jaeger |
| Trace → logs | Jaeger datasource com `tracesToLogsV2: {datasourceUid: loki, filterByTraceID: true, spanStartTimeShift: "-5m", spanEndTimeShift: "5m", tags: [{key: "service.name", value: "service"}], customQuery: true, query: '{service="${__span.tags["service.name"]}"} \| trace_id="${__trace.traceId}"'}`: o botão "Logs for this span" abre o Loki filtrado pelo trace |
| Trace → métricas | Jaeger datasource com `tracesToMetrics: {datasourceUid: prometheus, tags: [{key: "service.name", value: "job"}]}` e queries de taxa e latência do serviço do span |
| Log → trace | Loki datasource com `derivedFields: [{name: TraceID, matcherType: label, matcherRegex: trace_id, datasourceUid: jaeger, url: "$${__value.raw}"}]`, lendo o `trace_id` da structured metadata (com fallback por regex `"trace_id":"(\w+)"` na linha) |
| Log → métricas | Painéis de logs e de métricas no mesmo dashboard, com a mesma variável `service` e o mesmo intervalo de tempo |

Para isso funcionar, o `job` do scrape no Prometheus tem o mesmo nome do `service.name` do OTel e do label `service` do Loki (`agent`, `mcp-server`). Esse alinhamento de nomes é a cola da correlação e fica registrado no CLAUDE.md.

**Validação manual** (também em `docs/observabilidade.md`): rodar o validador, copiar o trace-id da primeira linha, abrir o dashboard **Correlação** e conferir: logs do agente e do MCP para o trace, o trace no Jaeger com os dois `tools/call` de ids diferentes e, a partir de um span, o salto para os logs dele.

## 12. Fase 8: versão, Docker e sistemas operacionais

1. **`VERSION`** = `0.1.0`. Python: `config.get_version()` lê o arquivo (caminho em `VERSION_FILE`, padrão: subir diretórios até achá-lo; no container ele é copiado para `/app/VERSION`). Makefile: `VERSION := $(shell cat VERSION)` e `make version`.
2. **Dockerfiles** (um por processo), multi-stage: `python:3.14-slim` (tag com digest travado) + `uv sync --frozen --no-dev`; usuário não root; `HEALTHCHECK` em `/healthz`; labels OCI com `org.opencontainers.image.version=$(VERSION)`.
3. **Imagens** `desafio-a2a/mcp-server:$(VERSION)` e `desafio-a2a/agent:$(VERSION)`:
   - `make build`: plataforma nativa (`--load`);
   - `make build-multiarch`: `docker buildx build --platform linux/amd64,linux/arm64`, que cobre Ubuntu amd64 e macOS Intel/Apple Silicon (as duas arquiteturas rodam Linux dentro do Colima).
4. **SO suportado** (`scripts/check_os.sh`, chamado por `make check-os` e como pré-requisito de `install`, `up` e `build`):
   - Linux: `/etc/os-release` com `ID=ubuntu`, `VERSION_ID` em `22.04 | 24.04 | 26.04` e `uname -m = x86_64`;
   - macOS: `uname -s = Darwin`, `uname -m` em `x86_64 | arm64`;
   - fora disso: erro com o SO e a arquitetura detectados e um link para `REQUIREMENTS.md`.
5. **macOS usa Colima, não Docker Desktop**: `brew install colima docker docker-compose docker-buildx` e `colima start --cpu 2 --memory 4`. O Makefile checa `colima status` e orienta se a VM estiver parada.
6. **Compose** (`docker-compose.yml`): serviços `mcp-server` (monta `./dados:/app/dados:ro`, healthcheck), `agent` (`depends_on: mcp-server: condition: service_healthy`, `MCP_URL=http://mcp-server:${MCP_PORT}/mcp`), `prometheus` (com `--enable-feature=exemplar-storage`), `grafana` (`depends_on` prometheus, jaeger e loki), `jaeger`, `loki` (volume nomeado) e `alloy` (`/var/run/docker.sock:ro`, `depends_on: loki`). Todas as imagens com versão travada e multi-arch (amd64 e arm64). `mcp-server` e `agent` recebem `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318` e não dependem de nenhum serviço de observabilidade para subir. Logs em stderr, visíveis com `make logs-mcp`.

## 13. Fase 9: Makefile e mise

**`mise.toml`**: `python = "3.14.x"` e `uv = "x.y.z"`, travados. Docker e Compose vêm do SO, não do mise.

**Alvos do Makefile** (com `make help` autodocumentado; cada alvo imprime o que está fazendo e, em caso de falha, a causa provável e como corrigir):

| Alvo | O que faz |
|---|---|
| `help` | lista os alvos |
| `version` | imprime o `VERSION` |
| `check-os` | valida SO e arquitetura |
| `check-dependencies` | checa mise, python, uv, docker, docker compose v2, buildx, daemon ativo (Colima no macOS) e portas livres; para o que faltar, imprime a URL oficial de instalação |
| `install` | instala o mise no diretório do usuário (`curl https://mise.run \| sh`, sem sudo), `mise install`, `uv sync` nos dois projetos, cria o `.env` a partir do `.env.example` e gera o secret. Não instala nada globalmente nem instala o Docker |
| `secret` | gera `REQUEST_STATE_SECRET` (`python3 -c "import secrets; print(secrets.token_hex(32))"`) no `.env` só se estiver vazio |
| `build` / `build-multiarch` | imagens com a tag do `VERSION` |
| `up` | `check-ports` + `docker compose up -d --wait` + mostra as URLs |
| `down` | `docker compose down` |
| `restore` | restaura os dados iniciais: recria `mcp-server` e `agent` (estado em memória volta a `dados/*.json`) e aguarda o healthcheck |
| `restart-mcp` | reinicia só o servidor MCP (prova do `requestState` após restart) |
| `logs`, `logs-mcp`, `logs-agent` | segue os logs |
| `traces` | mostra a URL da UI do Jaeger e checa se ela responde; com `TRACE_ID=<id>`, imprime o link direto do trace (ex.: o trace-id impresso pelo validador) |
| `observability` | checa a saúde de Prometheus, Grafana, Jaeger, Loki (`/ready`) e Alloy e imprime as URLs; com `TRACE_ID=<id>`, imprime o link do dashboard **Correlação** já filtrado |
| `run-mcp`, `run-agent` | sobe localmente sem Docker, um por terminal (fluxo do avaliador) |
| `validate` | `restore` + `python3 validador/validar.py --agente ... --mcp ...` |
| `test-unit` | `up` → pytest unit → `down` (sempre executa o `down`, mesmo com falha) e mostra o resumo |
| `test-integration` | `up` → `restore` → pytest integration → `down` e mostra o resumo |
| `tests` | unit + integração + validador, com `up` antes e `down` depois |
| `lint`, `fmt` | ruff |
| `toc` | roda `scripts/toc.py` em todos os `.md` permitidos |
| `clean` | remove caches e `.venv` |

Os alvos de teste usam o padrão `$(MAKE) up && (pytest ...; rc=$$?; $(MAKE) down; exit $$rc)` para garantir o `down` e preservar o código de saída.

**Portas em uso**: `scripts/check_ports.sh` testa `AGENT_PORT`, `MCP_PORT`, `PROMETHEUS_PORT`, `GRAFANA_PORT`, `JAEGER_UI_PORT`, `JAEGER_OTLP_HTTP_PORT`, `LOKI_PORT` e `ALLOY_UI_PORT` (`ss -ltn` no Linux, `lsof -iTCP -sTCP:LISTEN` no macOS) e, se alguma estiver ocupada, mostra o processo e sugere: `export MCP_PORT=7311 && make up`.

## 14. Fase 10: testes

**Unitários** (pytest, sem rede), por processo:
- servidor: parse de datas, cada validação e a ordem delas, sobreposição, alternativas (ordem, limite 3, empate por id, capacidade), selagem/verificação/expiração do `requestState` (adulteração de 1 caractere → rejeição), extração da versão da política, ids sequenciais;
- agente: parser dos dois formatos, máquina de estados (transições válidas e inválidas, terminal definitivo), `traceparent` (mantém trace-id, gera span-id novo, header inválido, contexto da Task reutilizado na continuação sem header, funcionamento com `OTEL_SDK_DISABLED=true`), spans com `InMemorySpanExporter` (hierarquia esperada e nenhum atributo contendo o `requestState`), formatação de `alternativas: `, serialização da Task sem `requestState`, ids JSON-RPC sempre novos, headers MCP espelhados (com o transporte mockado via `respx`).

**Integração** (pytest + httpx contra os containers), cobrindo os 13 passos do fluxo do avaliador:
1. card fiel a `07-a2a-agent-card.json`;
2. log do MCP com `tools/list` antes do primeiro `tools/call` e com o trace-id enviado (lido via `docker compose logs mcp-server`);
3. par de `tools/call` da pausa com ids diferentes;
4. garagem 14h–15h → `INPUT_REQUIRED` com `alternativas: sala-fusca, sala-mirante`; `escolha=sala-mirante` → `COMPLETED` + `politica`;
5. repetição com `escolha=recusar` → `CANCELED`;
6. `sala-inexistente` → `FAILED` com a mensagem exata;
7. `requestState` adulterado → `-32602`;
8. retry válido após `make restart-mcp` → reserva concluída;
9. conflito sem capability → `-32021` + HTTP 400;
10. extras: Task terminal recusa `SendMessage`, escolha inválida mantém a pausa, duas Tasks pausadas em paralelo, `requestState` ausente de todas as respostas A2A, determinismo;
11. traces: depois de um fluxo com pausa e retomada, `GET http://localhost:${JAEGER_UI_PORT}/api/traces/<trace-id>` (com tentativas até o batch ser exportado) traz spans dos serviços `agent` e `mcp-server` no mesmo trace-id enviado no header A2A, incluindo os dois `tools/call` com ids diferentes;
12. logs: `GET http://localhost:${LOKI_PORT}/loki/api/v1/query_range` com `{service=~"agent|mcp-server"} | trace_id="<trace-id>"` (com tentativas) devolve linhas dos dois serviços, incluindo o `tools/list` e os `tools/call` do MCP;
13. Grafana: `GET /api/datasources` lista `prometheus`, `jaeger` e `loki` com os UIDs fixos; `GET /api/datasources/uid/<uid>/health` responde OK para os três; os 5 dashboards estão provisionados (4 do projeto + Jaeger 24836); serviços, operações e trace por id do Jaeger respondem pelo Grafana; o Prometheus coleta o job `jaeger`;
14. resiliência: com `docker compose stop jaeger loki alloy`, o fluxo completo continua passando e o stderr do MCP continua registrando o `traceparent`.

Os unitários ganham testes do formatador de log JSON (sempre com `trace_id`/`span_id`, nunca com `requestState`) e da emissão de exemplars nos histogramas.

Cada teste de integração chama `restore` (fixture) para começar do estado inicial. A suíte termina rodando o `validador/validar.py` e exigindo código de saída 0 nas 36 verificações.

## 15. Fase 11: documentação

Tudo em pt-BR, com TOC no início e diagramas Mermaid acompanhados de analogias para iniciantes.

- **`README.md`** (substitui o do starter) com as 4 seções exigidas: *Como rodar* (de um clone limpo, com Docker e sem Docker), *Onde a ponte acontece* (links para as linhas de `bridge.py` em que o `input_required` vira `TASK_STATE_INPUT_REQUIRED` e em que o `requestState` volta ao servidor), *Decisões técnicas* (AES-256-GCM do SDK, TTL de 10 min, `TaskStore` em memória, segredo no `.env`), *Saída do validador* (colada completa da última execução). Além disso: portas e variáveis, links para `docs/`.
- **`docs/`**:
  - `arquitetura.md`: `flowchart` dos dois processos + Prometheus/Grafana/Jaeger/Loki/Alloy. Analogia: o agente é a recepcionista de um prédio, que fala com o visitante (A2A) e liga para o ramal da administração (MCP);
  - `fluxos.md`: `sequenceDiagram` do caminho feliz, do conflito com MRTR, da recusa, do erro e do retry após restart. Analogia do MRTR: o garçom não fica parado na mesa; ele anota, volta à cozinha e retorna com um novo pedido;
  - `maquina-de-estados.md`: `stateDiagram-v2` da Task. Analogia: senha de atendimento no balcão;
  - `request-state.md`: selagem/verificação. Analogia: envelope lacrado com selo de cera: dá para ler, mas não para alterar sem que se perceba;
  - `classes.md`: `classDiagram` dos módulos dos dois processos;
  - `testes.md`: pirâmide de testes e o fluxo `make tests` (`flowchart`);
  - `observabilidade.md`: métricas, dashboards, logs (LogQL de exemplo) e como acessar; `flowchart` dos três sinais (métricas → Prometheus, traces → Jaeger, logs → Alloy → Loki, tudo no Grafana) e `flowchart` dos links de correlação. Analogia: investigação de um acidente. As métricas são o velocímetro (quanto e quão rápido), o trace é o GPS com o trajeto completo e os logs são a caixa-preta com cada evento; o trace-id é a placa do carro que liga os três;
  - `tracing.md`: `sequenceDiagram` do `traceparent` atravessando A2A → agente → `_meta` → MCP → Jaeger, a árvore de spans de um pedido com pausa, e como achar no Jaeger o trace-id impresso pelo validador. Analogia: código de rastreio de encomenda; o trace-id é o código, e cada span é uma parada registrada (centro de distribuição, caminhão, entrega);
  - `api-swagger.md`, `variaveis-de-ambiente.md`, `troubleshooting.md` (erro → causa raiz → correção), `glossario.md`, `decisoes-tecnicas.md`.
- **`CONTRIBUTING.md`**: fluxo de branch e commit, `make check-os` → `make check-dependencies` → `make install`, padrão de código (en-US, ruff), docs (pt-BR, TOC, Mermaid), como rodar os testes e o validador antes do PR, arquivos proibidos.
- **`REQUIREMENTS.md`** (genérico): explica como detectar o SO (`make check-os`) e redireciona para `REQUIREMENTS-UBUNTU.md` ou `REQUIREMENTS-MACOS.md`. Cada um tem: (a) o caminho automático (`make check-os`, `make check-dependencies`, `make install`) e (b) o manual, com links oficiais: Docker Engine para Ubuntu (docs.docker.com/engine/install/ubuntu), Compose plugin (docs.docker.com/compose/install/linux), Docker para usar sem sudo (docs.docker.com/engine/install/linux-postinstall), mise (mise.jdx.dev/getting-started.html), Colima (github.com/abiosoft/colima), Homebrew (brew.sh), uv (docs.astral.sh/uv).
- **`scripts/toc.py`** (stdlib apenas):
  - TOC no início do arquivo, delimitado por `<!-- TOC -->` na abertura **e** no fechamento (sem `<!-- /TOC -->`, que conflita com plugins);
  - lista todos os níveis, **incluindo o `#`**, aninhando por nível como o plugin Markdown All in One; âncoras no padrão do GitHub (minúsculas, acentos mantidos, pontuação removida, espaços → `-`, sufixo `-1`, `-2` para duplicados);
  - ignora títulos dentro de blocos de código e o próprio bloco de TOC;
  - idempotente: se o par de marcadores existe, substitui o conteúdo; se não existe, insere; rodar duas vezes não altera nada (teste unitário garante);
  - nunca toca em `dados/`, `validador/`, `exemplos/` nem em `TASK.md`.

## 16. Fase 12: CLAUDE.md

Criar o `CLAUDE.md` com as instruções e guardrails para manter o repositório consistente com o TASK.md:

1. **Fonte de verdade**: TASK.md + `exemplos/wire/` + `validador/validar.py`; em caso de dúvida, o wire vence.
2. **Proibições**: alterar `dados/`, `validador/` e `exemplos/`; LLM no caminho de execução; segredo versionado; expor ou interpretar o `requestState` no agente; regra de sala no agente; sessão de protocolo; colapsar os dois processos em um.
3. **Contratos imutáveis**: as mensagens de erro exatas, a linha `alternativas: `, os códigos `-32602`/`-32021`/`-32020`, os nomes de tool, a skill e as portas padrão.
4. **Idiomas**: docs em pt-BR, código e comentários em en-US.
5. **Markdown**: todo `.md` novo ou alterado tem TOC no início entre dois `<!-- TOC -->`, incluindo o `#`; rodar `make toc` antes do commit.
6. **Diagramas e analogias**: ao mudar arquitetura, fluxo, estados, classes ou testes, atualizar o Mermaid correspondente em `docs/` e manter a analogia para iniciantes.
7. **Versão**: `VERSION` é a fonte única; nenhum outro arquivo fixa a versão.
8. **Atualização de dependências, somente quando solicitada explicitamente**: atualizar para as versões estáveis mais recentes, a partir de fontes oficiais, as ferramentas do `mise.toml`, os pins dos `pyproject.toml` (+ `uv lock`), as imagens base dos Dockerfiles, as imagens de Prometheus, Grafana, Jaeger, Loki e Alloy (conferindo se a configuração do Loki/Alloy e o provisionamento dos datasources do Grafana continuam válidos na nova versão), os pacotes `opentelemetry-*` (sempre na mesma versão entre si), o `swagger-ui-dist`, as versões de Ubuntu/macOS suportadas no `check_os.sh` e os `REQUIREMENTS*.md` (comandos e links). Depois, rodar `make tests` e `make validate` e atualizar a saída do validador no README.
9. **Tracing**: o OpenTelemetry é um extra. O log do `traceparent` no stderr do MCP é obrigatório e continua existindo; o `requestState` nunca vai para spans nem para logs; o sistema precisa funcionar com Jaeger, Loki e Alloy parados.
   **Correlação**: o nome do serviço é o mesmo no `job` do Prometheus, no `service.name` do OTel e no label `service` do Loki (`agent`, `mcp-server`); os UIDs dos datasources do Grafana (`prometheus`, `jaeger`, `loki`) são fixos; toda linha de log JSON leva `trace_id` e `span_id`. Mudou um desses nomes, atualizar provisionamento, dashboards e docs juntos.
10. **Definição de pronto**: `make tests` verde, validador com 36/36 e código 0, README com as 4 seções.

## 17. Variáveis de ambiente

Documentadas em `.env.example` (sem valores) e em `docs/variaveis-de-ambiente.md`:

| Variável | Padrão | Uso |
|---|---|---|
| `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | `127.0.0.1` (local; `0.0.0.0` no container) / `7301` / `/mcp` | bind do servidor MCP |
| `AGENT_HOST` / `AGENT_PORT` / `AGENT_PATH` | `127.0.0.1` (local; `0.0.0.0` no container) / `7300` / `/a2a` | bind do agente |
| `AGENT_PUBLIC_URL` | `http://127.0.0.1:${AGENT_PORT}/a2a` | URL publicada no card |
| `MCP_URL` | `http://127.0.0.1:${MCP_PORT}/mcp` | onde o agente encontra o MCP |
| `REQUEST_STATE_SECRET` | (obrigatória, ≥ 32 bytes) | chave do selo AEAD do `requestState` |
| `REQUEST_STATE_TTL_SECONDS` | `600` | validade, entre 300 e 1800 |
| `DATA_DIR` | `./dados` | origem dos JSON e da política |
| `LOG_LEVEL` | `INFO` | nível de log |
| `PROMETHEUS_PORT` / `GRAFANA_PORT` | `9090` / `3000` | observabilidade |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | (sem valor) | credenciais do Grafana |
| `JAEGER_UI_PORT` / `JAEGER_OTLP_HTTP_PORT` | `16686` / `4318` | UI do Jaeger / OTLP publicado no host |
| `LOKI_PORT` / `ALLOY_UI_PORT` | `3100` / `12345` | API do Loki / UI de debug do Alloy |
| `LOKI_RETENTION_PERIOD` | `72h` | retenção dos logs no Loki |
| `LOG_FORMAT` | `json` | `json` (padrão, usado pelo Loki) ou `text` para leitura humana no terminal |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://jaeger:4318` no compose; vazio fora dele | destino dos traces (vazio = sem exportação) |
| `OTEL_SERVICE_NAME` | `agent` / `mcp-server` | nome do serviço no Jaeger |
| `OTEL_TRACES_SAMPLER` | `parentbased_always_on` | amostragem |
| `OTEL_SDK_DISABLED` | `false` | desliga o OTel por completo |
| `VERSION_FILE` | auto | caminho do `VERSION` |

Se uma porta já estiver em uso, o processo Python captura o `OSError` do bind e termina com `Port 7301 is already in use. Set MCP_PORT to a free port (e.g. MCP_PORT=7311).` Se o validador for usado com outras portas, basta passar `--agente`/`--mcp`.

## 18. Rastreabilidade das 36 verificações

| # | Verificação | Fase |
|---|---|---|
| 01–03 | tools/list, inputSchema objeto, `listar_salas` texto = estruturado | 1 |
| 04–05 | `_meta` incompleto → -32602 + 400 | 1 |
| 06 | tool inexistente recusada | 1 |
| 07–08 | resource da política / URI inexistente -32602 | 1 |
| 09–12 | mensagens exatas de sala, janela, duração e intervalo | 1 |
| 13–14 | `input_required`, form mode, enum `[sala-fusca, sala-mirante]` | 2 |
| 15 | -32021 sem capability | 2 |
| 16 | retry conclui na sala escolhida | 2 |
| 17 | `requestState` adulterado → -32602 | 2 |
| 18 | argumentos adulterados não tomam efeito (usar os selados) | 2 |
| 19 | decline sem `isError`, `reservado: false` | 2 |
| 20 | sem alternativas → mensagem exata | 2 |
| 21–23 | card 200, interface JSONRPC 1.0, skill | 4 |
| 24–26 | Task COMPLETED, artifact `reserva` com `politica`, GetTask | 3, 4 |
| 27–28 | pausa + linha de alternativas | 5 |
| 29 | escolha fora do enum mantém a pausa | 5 |
| 30 | continuação conclui na sala escolhida | 5 |
| 31 | Task terminal recusa `SendMessage` | 4 |
| 32 | recusar → CANCELED | 5 |
| 33 | duas Tasks pausadas, cada uma com a sua reserva | 5 |
| 34 | `requestState` nunca nas respostas A2A | 5 |
| 35 | sala inexistente → FAILED com a mensagem da tool | 3 |
| 36 | determinismo da pausa | 3, 5 |

Observação: o validador depende do estado inicial (as verificações 16, 18 e 20 criam reservas que mudam as alternativas das verificações 32 e 33), por isso `make validate` sempre roda `restore` antes.

## 19. Riscos e pontos em aberto

| Risco | Mitigação |
|---|---|
| API exata do MRTR no SDK `mcp` v2 desconhecida antes do spike | Fase 0 dedicada; ler as docstrings de `input_required` antes de escrever a tool |
| Cliente MCP do SDK resolve a elicitation sozinho | Não registrar callback; se ainda assim não expuser o resultado cru, usar cliente `httpx` fino e documentar a evidência |
| Alguma dependência (`mcp`, `a2a-sdk`, `pydantic-core`, `prometheus-client`) sem wheel ou suporte para Python 3.14 | Conferir no spike da Fase 0 (`uv sync` com 3.14 nas duas arquiteturas); se faltar, documentar a evidência no README e travar a versão compatível mais recente |
| `a2a-sdk` divergir do formato do wire v1.0 | Implementação fina do JSON-RPC em Starlette (2 métodos) |
| Docker Engine ainda sem repositório oficial para Ubuntu 26.04 | Checar na documentação oficial na hora da implementação; se faltar, documentar o fallback oficial no `REQUIREMENTS-UBUNTU.md` |
| Cardinalidade de labels (`responsible`, `date`) | Aceitável no volume do desafio; documentado em `observabilidade.md` |
| Secret diferente entre restarts invalidaria o teste de restart | Secret persistido no `.env`, gerado só se vazio |
| Pacotes `opentelemetry-*` sem suporte a Python 3.14 | Conferir no spike da Fase 0; como o tracing é opcional, dá para desligar com `OTEL_SDK_DISABLED=true` sem afetar o desafio |
| Traces fragmentados entre o pedido inicial e a continuação | Contexto OTel guardado na Task e reutilizado quando a continuação chega sem `traceparent` |
| Auto-instrumentação injetar um `traceparent` HTTP divergente do `_meta` | Não usar auto-instrumentação do `httpx`; o `_meta.traceparent` é a única fonte |
| Alloy precisa do socket do Docker (no macOS, dentro da VM do Colima) | Montagem `:ro` do `/var/run/docker.sock` no compose, que roda no mesmo contexto Docker; `make check-dependencies` confere o `docker context` ativo |
| Cardinalidade alta no Loki (`trace_id`, `task_id`) | Ficam em structured metadata, não em labels; labels só `service`, `container`, `stream`, `level` |
| Exemplars não aparecem | Exigem exposição OpenMetrics + `exemplar-storage` no Prometheus; teste unitário cobre a emissão e o checklist confere no Grafana |
| Pastas e versões de provisionamento do Grafana mudam entre versões | Versão do Grafana travada; teste de integração confere datasources e dashboards via API |
| Middleware de log consumir o corpo do request | Middleware ASGI que faz buffer e reinjeta o `receive` |

## 20. Checklist final de entrega

- [ ] `make check-os`, `make check-dependencies` e `make install` funcionam em Ubuntu 22.04/24.04/26.04 amd64 e macOS amd64/arm64 com Colima
- [ ] `make up` sobe os 7 serviços; Swagger em `:7300/docs` e `:7301/docs`; Grafana com os 4 dashboards e os datasources Prometheus, Jaeger e Loki saudáveis; Jaeger em `:16686`
- [ ] O trace-id impresso pelo validador aparece no Jaeger com spans de `agent` e `mcp-server` e no Loki com logs dos dois serviços
- [ ] No Grafana: exemplar → trace, span → logs, log → trace e trace → métricas funcionando
- [ ] Tudo continua passando com Jaeger, Loki e Alloy parados
- [ ] `make tests` verde (unit + integração + validador), com `up`/`down` automáticos
- [ ] `python3 validador/validar.py` → 36/36, código de saída 0, com os processos recém-iniciados
- [ ] Passos 1–13 do fluxo do avaliador conferidos manualmente com `curl`
- [ ] `git diff --stat origin/main -- dados validador exemplos` vazio
- [ ] Nenhum segredo versionado; `.env` ignorado; `.env.example` só com nomes
- [ ] Nenhuma dependência de LLM nos `pyproject.toml`
- [ ] README com as 4 seções e a saída do validador atualizada; `docs/` completa com Mermaid e analogias
- [ ] `CLAUDE.md`, `CONTRIBUTING.md`, `REQUIREMENTS*.md` criados; `make toc` idempotente (segunda execução sem diff)
- [ ] Clone limpo do fork, seguindo apenas o README, reproduz tudo
