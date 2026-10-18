<!-- TOC -->
- [Variáveis de ambiente](#variáveis-de-ambiente)
  - [Segredos (obrigatórios)](#segredos-obrigatórios)
  - [Servidor MCP](#servidor-mcp)
  - [Agente](#agente)
  - [Logs e observabilidade](#logs-e-observabilidade)
  - [Porta ocupada?](#porta-ocupada)
<!-- TOC -->

# Variáveis de ambiente

Todas ficam no `.env` (criado por `make install` ou `make secret` a partir do [.env.example](../.env.example), que só tem os nomes). Valor vazio usa o padrão. Variáveis exportadas no shell têm prioridade sobre o `.env` nos scripts do Makefile.

## Segredos (obrigatórios)

| Variável | Uso |
|---|---|
| `REQUEST_STATE_SECRET` | chave de integridade do `requestState`, com pelo menos 32 bytes aleatórios. `make secret` gera; manualmente: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `GRAFANA_ADMIN_PASSWORD` | senha do usuário admin do Grafana (gerada por `make secret`) |

## Servidor MCP

| Variável | Padrão | Uso |
|---|---|---|
| `MCP_HOST` | `127.0.0.1` local, `0.0.0.0` no container | interface de escuta. Com 127.0.0.1 o SDK liga a proteção contra DNS rebinding |
| `MCP_PORT` | `7301` | porta (local) ou porta publicada no host (compose) |
| `MCP_PATH` | `/mcp` | endpoint Streamable HTTP |
| `REQUEST_STATE_TTL_SECONDS` | `600` | validade do `requestState`, entre 300 e 1800 |
| `DATA_DIR` | `./dados` (busca automática) | origem de `salas.json`, `reservas.json` e `politica-de-uso.md` |

## Agente

| Variável | Padrão | Uso |
|---|---|---|
| `AGENT_HOST` | `127.0.0.1` local, `0.0.0.0` no container | interface de escuta |
| `AGENT_PORT` | `7300` | porta (local) ou porta publicada no host (compose) |
| `AGENT_PATH` | `/a2a` | endpoint JSON-RPC |
| `AGENT_PUBLIC_URL` | `http://127.0.0.1:${AGENT_PORT}/a2a` | URL publicada no Agent Card |
| `MCP_URL` | `http://127.0.0.1:${MCP_PORT}/mcp` local; `http://mcp-server:7301/mcp` no compose | onde o agente encontra o servidor MCP |
| `MCP_TIMEOUT_SECONDS` | `10` | timeout de cada request MCP |

## Logs e observabilidade

| Variável | Padrão | Uso |
|---|---|---|
| `LOG_LEVEL` | `INFO` | nível de log dos dois processos |
| `LOG_FORMAT` | `json` | `json` (usado pelo Loki) ou `text` (leitura no terminal) |
| `PROMETHEUS_PORT` | `9090` | porta do Prometheus no host |
| `GRAFANA_PORT` / `GRAFANA_ADMIN_USER` | `3000` / `admin` | Grafana |
| `JAEGER_UI_PORT` / `JAEGER_OTLP_HTTP_PORT` | `16686` / `4318` | UI do Jaeger / OTLP publicado no host (para `make run-*`) |
| `LOKI_PORT` / `LOKI_RETENTION_PERIOD` | `3100` / `72h` | Loki |
| `ALLOY_UI_PORT` | `12345` | UI de depuração do Alloy |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://jaeger:4318` no compose; vazio fora dele | destino dos traces (vazio = sem exportação) |
| `OTEL_SDK_DISABLED` | `false` | desliga o OpenTelemetry por completo |
| `OTEL_SERVICE_NAME` | `agent` / `mcp-server` | nome do serviço nos traces (mantenha os padrões: a correlação depende deles) |
| `VERSION_FILE` | busca automática | caminho do arquivo `VERSION` |

## Porta ocupada?

`make up` e `make check-dependencies` rodam [scripts/check_ports.sh](../scripts/check_ports.sh), que mostra qual processo ocupa a porta e sugere a troca:

```text
[fail] Port 7301 (MCP_PORT) is already in use: LISTEN 0 5 0.0.0.0:7301 ... users:(("python3",pid=4036115,fd=3))
[fail]   -> pick another one, e.g.: echo 'MCP_PORT=7311' >> .env   (or: export MCP_PORT=7311)
```

No compose, as variáveis `*_PORT` mudam só a porta publicada no host; dentro da rede do compose os serviços usam sempre as portas padrão. Rodando localmente (`make run-mcp`/`make run-agent`), o próprio processo detecta a porta ocupada e para com a mesma orientação. Para o validador com portas trocadas:

```bash
python3 validador/validar.py --agente http://localhost:7310 --mcp http://localhost:7311
```
