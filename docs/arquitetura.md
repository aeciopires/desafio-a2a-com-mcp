<!-- TOC -->
- [Arquitetura](#arquitetura)
  - [A ideia em uma frase](#a-ideia-em-uma-frase)
  - [Visão geral dos processos](#visão-geral-dos-processos)
  - [Camadas do servidor MCP](#camadas-do-servidor-mcp)
  - [Camadas do agente](#camadas-do-agente)
  - [Observabilidade em volta](#observabilidade-em-volta)
  - [Onde ficam as coisas](#onde-ficam-as-coisas)
<!-- TOC -->

# Arquitetura

## A ideia em uma frase

O **agente** é a recepção de um prédio: quem chega de fora (outro agente, via **A2A**) fala só com a recepcionista. Ela não decide nada sobre as salas; liga para o ramal da administração (o **servidor MCP**), que conhece as regras, e repassa a resposta. Quando a administração diz "essa sala está ocupada, qual destas serve?", a recepcionista não escolhe por conta própria: devolve a pergunta ao visitante e guarda o protocolo da ligação até ele responder.

## Visão geral dos processos

```mermaid
flowchart LR
    subgraph Cliente["Cliente A2A (validador, outro agente, curl)"]
        C[SendMessage / GetTask<br/>header traceparent]
    end

    subgraph Agente["agente :7300 (processo 1)"]
        Card[/.well-known/agent-card.json/]
        RPC[a2a_rpc.py<br/>JSON-RPC A2A v1.0]
        Tasks[(TaskStore<br/>em memória)]
        Bridge[bridge.py<br/>A PONTE]
        Host[mcp_host.py<br/>cliente MCP]
    end

    subgraph MCP["servidor-mcp :7301 (processo 2)"]
        MW[observability_mw.py<br/>log stderr + span + métricas]
        SDK[SDK oficial MCP<br/>Streamable HTTP stateless<br/>RequestStateBoundary]
        Tools[server.py<br/>3 tools + resource]
        Domain[domain.py + service.py<br/>regras de sala]
        Repo[(Repository<br/>em memória)]
    end

    Dados[(dados/*.json<br/>politica-de-uso.md)]

    C -->|HTTP JSON-RPC| RPC
    C -->|GET| Card
    RPC --> Tasks
    RPC --> Bridge
    Bridge --> Host
    Host -->|HTTP POST /mcp<br/>_meta completo em cada request| MW
    MW --> SDK --> Tools --> Domain --> Repo
    Dados -->|carga no boot| Repo
```

- **Dois processos separados**, falando HTTP como cliente e servidor MCP de verdade. Nenhum importa código do outro.
- **O agente traduz protocolo, não domínio.** Conflito, política e alternativas são decididos só no servidor MCP.
- **Nenhum dos lados tem sessão.** Cada request MCP leva `protocolVersion` e `clientCapabilities` no `_meta`; o estado de uma pausa viaja no `requestState` (MCP) e fica guardado na Task (A2A).

## Camadas do servidor MCP

```mermaid
flowchart TB
    HTTP[POST /mcp] --> MW["McpObservabilityMiddleware<br/>(lê o corpo, loga method/id/traceparent,<br/>abre o span, mede)"]
    MW --> T["Transporte Streamable HTTP do SDK<br/>valida _meta (-32602/400),<br/>headers espelhados (-32020)"]
    T --> B["RequestStateBoundary do SDK<br/>verifica/sela o requestState<br/>(AES-256-GCM + TTL + binding)"]
    B --> R["Resolver escolha_de_sala<br/>(decide se precisa perguntar)"]
    R -->|sala livre| Body[Corpo da tool reservar_sala]
    R -->|conflito| IR["Elicit → InputRequiredResult<br/>(input_required + requestState)"]
    R -->|regra violada| Err["ToolError → isError: true"]
    Body --> S[BookingService / domain.py]
```

Analogia do servidor: é um **cartório**. Ele não guarda conversa com ninguém; cada pedido precisa vir com todos os documentos (o `_meta`). Quando falta uma informação, o cartório entrega um **envelope lacrado** (o `requestState`) com tudo o que já foi analisado e pede que você volte com ele e com a resposta. Se o lacre estiver violado, o pedido é recusado.

## Camadas do agente

```mermaid
flowchart TB
    In[POST /a2a] --> RPC["A2AHandler<br/>(JSON-RPC, erros A2A)"]
    RPC -->|SendMessage sem taskId| New[TaskStore.create → SUBMITTED]
    RPC -->|SendMessage com taskId| Old[TaskStore.get + lock da Task]
    RPC -->|GetTask| Get[Task.to_wire]
    New --> Start[Bridge.start]
    Old --> Resume[Bridge.resume]
    Start --> Host[McpHost<br/>tools/list → resources/read → tools/call]
    Resume --> Host2[McpHost<br/>tools/call com id novo,<br/>inputResponses e requestState ecoado]
```

## Observabilidade em volta

```mermaid
flowchart LR
    A[agente] -- /metrics --> P[Prometheus]
    M[servidor-mcp] -- /metrics --> P
    A -- OTLP/HTTP spans --> J[Jaeger]
    M -- OTLP/HTTP spans --> J
    A -. stderr .-> D[(Docker logs)]
    M -. stderr .-> D
    D --> AL[Grafana Alloy] --> L[Loki]
    P --> G[Grafana]
    J --> G
    L --> G
```

Tudo isso é extra: o desafio exige apenas o log do `traceparent` no stderr do servidor MCP, e os dois processos funcionam com a stack de observabilidade parada. Detalhes em [observabilidade.md](observabilidade.md) e [tracing.md](tracing.md).

## Onde ficam as coisas

| Pasta | Conteúdo |
|---|---|
| [servidor-mcp/src/mcp_server/](../servidor-mcp/src/mcp_server/) | servidor MCP: `server.py` (tools, resource, MRTR), `domain.py` (regras), `observability_mw.py` (log/span/métricas) |
| [agente/src/agent/](../agente/src/agent/) | agente: `a2a_rpc.py` (A2A), `bridge.py` (a ponte), `mcp_host.py` (cliente MCP), `tasks.py` (Task) |
| [tests/integration/](../tests/integration/) | testes de ponta a ponta contra a stack em execução |
| [observability/](../observability/) | Prometheus, Loki, Alloy e Grafana (datasources e dashboards) |
| [scripts/](../scripts/) | checagens do Makefile, gerador de TOC e de dashboards |
