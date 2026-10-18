<!-- TOC -->
- [Solução de problemas](#solução-de-problemas)
  - [Onde olhar](#onde-olhar)
<!-- TOC -->

# Solução de problemas

Cada mensagem abaixo é emitida pelo Makefile, pelos scripts ou pelos processos, e aponta a causa raiz.

| Mensagem | Causa | Correção |
|---|---|---|
| `[fail] Unsupported Linux: ...` / `Unsupported architecture ...` | SO ou arquitetura fora da lista suportada | use Ubuntu 22.04/24.04/26.04 amd64 ou macOS amd64/arm64 ([REQUIREMENTS.md](../REQUIREMENTS.md)) |
| `[fail] Docker daemon is not reachable.` | Docker parado (Linux) ou VM do Colima parada (macOS) | `sudo systemctl start docker` / `colima start --cpu 2 --memory 4` |
| `permission denied while trying to connect to the Docker daemon socket` | usuário fora do grupo `docker` | https://docs.docker.com/engine/install/linux-postinstall/ |
| `[fail] .env not found. Run: make secret` | `.env` ainda não criado | `make secret` (ou `make install`) |
| `REQUEST_STATE_SECRET is not set. Run 'make secret'` (compose) | segredo vazio no `.env` | `make secret` |
| `[mcp-server] configuration error: REQUEST_STATE_SECRET must be at least 32 bytes` | segredo curto | gere com `make secret` (apague a linha antiga antes) |
| `[fail] Port 7301 (MCP_PORT) is already in use: ...` | outro processo na porta | troque a porta no `.env` ([variaveis-de-ambiente.md](variaveis-de-ambiente.md)) ou pare o processo |
| `startup failed: Port 7300 is already in use on 127.0.0.1` | `make run-agent` com a porta ocupada | idem |
| `The stack did not become healthy` | algum container falhou ao subir | `make ps` e `make logs` (procure `level: error`) |
| Task `FAILED` com `MCP server unreachable at http://...: ...` | o agente não alcança o servidor MCP | confira `MCP_URL` e se o servidor está de pé (`curl localhost:7301/healthz`) |
| Task `FAILED` com `Erro do servidor MCP (-32602): Invalid or expired requestState` | `requestState` expirou (TTL) ou o servidor reiniciou com **outro** segredo | refaça o pedido; mantenha o mesmo `REQUEST_STATE_SECRET` entre restarts |
| `[fail] dados/, validador/ or exemplos/ were modified.` | algum arquivo protegido foi alterado | `git checkout -- dados validador exemplos` |
| `OTLP export to http://jaeger:4318 failed ...` (aviso único) | Jaeger fora do ar | `make up` ou ignore: as requisições não são afetadas |
| Grafana mostra o datasource Jaeger com `request failed: 404 Not Found` | Jaeger 2.21+ não tem mais `/api/services`, e o Grafana subiu sem o feature toggle | confira `GF_FEATURE_TOGGLES_ENABLE: jaegerEnableGrpcEndpoint` no serviço `grafana` do compose e rode `docker compose up -d grafana` |
| Explore → Jaeger → *Search* falha com `404 Not Found` | o plugin do Grafana ainda usa `/api/traces` para busca (limitação conhecida) | busque na UI do Jaeger (http://localhost:16686) ou consulte pelo trace-id (*TraceID*) |
| Trace no Grafana falha com `cannot unmarshal bool into ... boolValue` | atributo de span bool ou double ([grafana-jaeger-datasource#83](https://github.com/grafana/grafana-jaeger-datasource/issues/83)) | grave o atributo como string, como em `mcp.retry` ([decisoes-tecnicas.md](decisoes-tecnicas.md)) |
| Dashboard **Jaeger V2 OpenTelemetry Metrics** vazio | o Prometheus não coleta `jaeger:8888` | confira o target `jaeger` em http://localhost:9090/targets |
| `Builder ... cannot build linux/arm64` | sem emulação QEMU para build multi-arch | `docker run --privileged --rm tonistiigi/binfmt --install arm64` |
| Validador com `FAIL` em 28/32/33 numa segunda execução | reservas da execução anterior ainda em memória | rode sempre com processos novos: `make validate` já faz `restore` |
| Validador com erro de sintaxe no macOS | Python do sistema é 3.9 (o validador exige 3.10+) | `make validate` (usa o Python do mise) ou `mise exec -- python validador/validar.py ...` |

## Onde olhar

```bash
make ps            # estado e saúde dos containers
make logs-mcp      # stderr do servidor MCP: uma linha JSON por request (method, id, traceparent)
make logs-agent    # transições de estado das Tasks e chamadas MCP
make observability # saúde de Prometheus, Grafana, Jaeger, Loki e Alloy
```

Com `LOG_FORMAT=text` os logs ficam mais legíveis no terminal (o Loki continua recebendo, só que sem parse de JSON).
