<!-- TOC -->
- [Fluxos da API e dos agentes](#fluxos-da-api-e-dos-agentes)
  - [1. Sala livre (caminho feliz)](#1-sala-livre-caminho-feliz)
  - [2. Sala ocupada: a ponte em ação (MRTR + INPUT_REQUIRED)](#2-sala-ocupada-a-ponte-em-ação-mrtr--input_required)
  - [3. Recusa](#3-recusa)
  - [4. Escolha inválida](#4-escolha-inválida)
  - [5. Erro de regra (sala inexistente, janela, duração, intervalo)](#5-erro-de-regra-sala-inexistente-janela-duração-intervalo)
  - [6. Retry depois de reiniciar o servidor MCP](#6-retry-depois-de-reiniciar-o-servidor-mcp)
  - [7. Rejeições de protocolo](#7-rejeições-de-protocolo)
<!-- TOC -->

# Fluxos da API e dos agentes

Todos os fluxos partem de um `SendMessage` no formato fixo `reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>`. A resposta a uma pausa é `escolha=<id>` ou `escolha=recusar`.

## 1. Sala livre (caminho feliz)

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente A2A
    participant A as Agente
    participant M as Servidor MCP
    C->>A: SendMessage "reservar sala=sala-porao ..." (traceparent)
    A->>A: Task SUBMITTED → WORKING
    A->>M: tools/list (id 1)
    M-->>A: 3 tools
    A->>M: resources/read politica://uso (id 2)
    M-->>A: "versao: 2026-11-01 ..."
    A->>M: tools/call reservar_sala (id 3)
    M-->>A: resultType complete, structuredContent.reservado = true
    A->>A: artifact "reserva" + Task COMPLETED
    A-->>C: Task COMPLETED com o artifact
```

Analogia: pedir uma mesa num restaurante vazio. O garçom confere o cardápio (`tools/list`), lê as regras da casa (`resources/read`) e confirma a mesa na hora.

## 2. Sala ocupada: a ponte em ação (MRTR + INPUT_REQUIRED)

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente A2A
    participant A as Agente (bridge.py)
    participant M as Servidor MCP
    C->>A: SendMessage "reservar sala=sala-garagem 14h-15h"
    A->>M: tools/list, resources/read
    A->>M: tools/call reservar_sala (id 6)
    Note over M: conflito com res-0001<br/>alternativas = [sala-fusca, sala-mirante]
    M-->>A: resultType input_required<br/>inputRequests {chave: elicitation/create form}<br/>requestState "v1.…" (lacrado)
    A->>A: guarda chave + requestState NA TASK<br/>Task → INPUT_REQUIRED
    A-->>C: "alternativas: sala-fusca, sala-mirante"
    Note over C,A: ninguém fica esperando:<br/>a requisição HTTP já terminou
    C->>A: SendMessage taskId + "escolha=sala-mirante"
    A->>A: Task → WORKING
    A->>M: tools/call reservar_sala (id 7, NOVO)<br/>mesmos arguments<br/>inputResponses {mesma chave: accept sala-mirante}<br/>requestState ecoado sem mudança
    Note over M: SDK verifica o lacre,<br/>reconstrói a rodada a partir do requestState
    M-->>A: resultType complete, reserva res-0005 na sala-mirante
    A-->>C: Task COMPLETED + artifact (com politica)
```

Analogia: o **garçom** volta da cozinha dizendo "acabou o peixe; pode ser frango ou massa?". Ele não fica parado ao lado do fogão esperando você decidir (não existe canal de volta); ele vai até a mesa, anota a resposta e faz um **pedido novo** para a cozinha, grampeado ao bilhete original.

Os pontos exatos do código estão no [README](../README.md#onde-a-ponte-acontece).

## 3. Recusa

```mermaid
sequenceDiagram
    participant C as Cliente A2A
    participant A as Agente
    participant M as Servidor MCP
    C->>A: SendMessage taskId + "escolha=recusar"
    A->>M: tools/call (id novo) inputResponses {chave: {action: decline}}
    M-->>A: complete, isError false, reservado false, motivo "recusado"
    A-->>C: Task CANCELED
```

## 4. Escolha inválida

```mermaid
sequenceDiagram
    participant C as Cliente A2A
    participant A as Agente
    C->>A: SendMessage taskId + "escolha=sala-aquario"
    Note over A: fora do enum recebido do servidor:<br/>não chama o MCP
    A-->>C: Task continua INPUT_REQUIRED<br/>"alternativas: sala-fusca, sala-mirante" (repetida)
```

## 5. Erro de regra (sala inexistente, janela, duração, intervalo)

```mermaid
sequenceDiagram
    participant C as Cliente A2A
    participant A as Agente
    participant M as Servidor MCP
    C->>A: SendMessage "reservar sala=sala-inexistente ..."
    A->>M: tools/call reservar_sala
    M-->>A: complete, isError true<br/>"Error executing tool reservar_sala: Sala inexistente: sala-inexistente"
    A-->>C: Task FAILED com a mensagem exata da tool no status e no histórico
```

## 6. Retry depois de reiniciar o servidor MCP

```mermaid
sequenceDiagram
    participant X as Cliente MCP
    participant M1 as Servidor MCP (antes)
    participant M2 as Servidor MCP (depois do restart)
    X->>M1: tools/call (conflito)
    M1-->>X: input_required + requestState
    Note over M1,M2: make restart-mcp<br/>memória zerada, mesmo REQUEST_STATE_SECRET
    X->>M2: tools/call (id novo) + inputResponses + requestState
    Note over M2: o estado viaja no requestState,<br/>não no servidor
    M2-->>X: complete, reserva criada
```

## 7. Rejeições de protocolo

| Situação | Resposta |
|---|---|
| `_meta` sem `protocolVersion` ou sem `clientCapabilities` | `-32602`, HTTP 400 |
| Header `Mcp-Method`/`Mcp-Name` diferente do corpo | `-32020` |
| Conflito vindo de cliente sem `elicitation.form` | `-32021`, HTTP 400, `data.requiredCapabilities` |
| `requestState` adulterado, expirado ou com argumentos trocados | `-32602` (`Invalid or expired requestState`) |
| `resources/read` de URI inexistente | `-32602` |
| `SendMessage` para Task terminal | erro A2A `-32004` (UnsupportedOperation) |
| `SendMessage`/`GetTask` de Task inexistente | erro A2A `-32001` (TaskNotFound) |
