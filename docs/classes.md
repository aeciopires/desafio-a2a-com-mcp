<!-- TOC -->
- [Classes e módulos](#classes-e-módulos)
  - [Servidor MCP](#servidor-mcp)
  - [Agente](#agente)
  - [Analogia](#analogia)
<!-- TOC -->

# Classes e módulos

## Servidor MCP

```mermaid
classDiagram
    direction LR
    class McpObservabilityMiddleware {
        +app
        +path
        +__call__(scope, receive, send)
        -_parse(body) dict
        -_outcome(raw) dict
    }
    class MCPServer {
        <<SDK oficial>>
        +tool()
        +resource()
        +streamable_http_app()
    }
    class RequestStateSecurity {
        <<SDK oficial>>
        keys
        ttl
    }
    class BookingService {
        +policy_version str
        +rooms() list~Room~
        +validate(tool, sala, inicio, fim) ValidRequest
        +availability(tool, sala, inicio, fim) Availability
        +alternatives(tool, request) list~str~
        +reserve(sala, inicio, fim, responsavel) Reservation
    }
    class Repository {
        +rooms dict
        +policy_text str
        +reservations() list~Reservation~
        +add(...) Reservation
        +from_data_dir(path)$ Repository
    }
    class Room {
        id
        nome
        capacidade
        recursos
    }
    class Reservation {
        id
        sala
        inicio
        fim
        responsavel
    }
    class DomainError {
        reason
        message
    }
    class ReservaOut {
        <<pydantic, contrato>>
        reserva
        reservado
        sala
        inicio
        fim
        responsavel
        politica
        motivo
    }
    McpObservabilityMiddleware --> MCPServer : envolve a app ASGI
    MCPServer --> RequestStateSecurity : sela/verifica requestState
    MCPServer ..> BookingService : tools e resolver escolha_de_sala
    BookingService --> Repository
    Repository o-- Room
    Repository o-- Reservation
    BookingService ..> DomainError : lança
    MCPServer ..> ReservaOut : structuredContent
```

`domain.py` não tem classes com comportamento: são funções puras (`validate_request`, `conflicts`, `alternatives`, `parse_policy_version`), fáceis de testar.

## Agente

```mermaid
classDiagram
    direction LR
    class A2AHandler {
        +handle(request) JSONResponse
        +send_message(params, traceparent) dict
        +get_task(params) dict
        -_continue(task, message)
        -_bind_trace(task, traceparent, span)
    }
    class TaskStore {
        +create(context_id) Task
        +get(task_id) Task
    }
    class Task {
        id
        context_id
        state TaskState
        status_message
        history
        artifacts
        -pending PendingInput
        -policy_version
        -trace_id
        +transition(state, text)
        +repeat_status()
        +add_artifact(name, text)
        +to_wire() dict
    }
    class PendingInput {
        <<privado da Task>>
        tool
        arguments
        input_key
        request_state
        allowed
    }
    class TaskState {
        <<enum>>
        SUBMITTED
        WORKING
        INPUT_REQUIRED
        COMPLETED
        FAILED
        CANCELED
    }
    class Bridge {
        +start(task, text)
        +resume(task, text)
        -_discover(task)
        -_apply(task, tool, args, result)
        -_pause(task, tool, args, result)
    }
    class McpHost {
        +request(method, params, name) dict
        +list_tools() list~Tool~
        +read_text_resource(uri) str
        +call_tool(name, args, input_responses, request_state)
        -_ids itertools.count
    }
    A2AHandler --> TaskStore
    A2AHandler --> Bridge
    TaskStore o-- Task
    Task *-- PendingInput
    Task --> TaskState
    Bridge --> McpHost : HTTP JSON-RPC
    Bridge ..> PendingInput : cria na pausa, consome no retry
```

Os resultados MCP são tipados com os modelos do SDK (`mcp_types.CallToolResult`, `mcp_types.InputRequiredResult`, `mcp_types.ElicitRequest`, `mcp_types.ElicitResult`).

## Analogia

- `McpHost` é o **telefone** da recepção: sabe discar (headers, `_meta`, ids novos), mas não sabe o que dizer.
- `Bridge` é a **recepcionista**: decide quando ligar, o que anotar e quando devolver a pergunta ao visitante.
- `Task` é a **ficha do atendimento**: o que o visitante vê (estado, histórico, produto) e um bolso interno (`PendingInput`) com o protocolo da ligação, que o visitante nunca vê.
