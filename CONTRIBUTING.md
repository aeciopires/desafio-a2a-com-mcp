<!-- TOC -->
- [Como contribuir](#como-contribuir)
  - [Preparar o ambiente](#preparar-o-ambiente)
  - [Fluxo de trabalho](#fluxo-de-trabalho)
  - [Convenções](#convenções)
  - [Arquivos que não podem mudar](#arquivos-que-não-podem-mudar)
  - [Onde mexer](#onde-mexer)
<!-- TOC -->

# Como contribuir

## Preparar o ambiente

```bash
make check-os              # sistema suportado? (Ubuntu 22.04/24.04/26.04 amd64, macOS amd64/arm64)
make install               # mise, Python, uv, dependências e .env
make check-dependencies    # Docker, Compose, buildx, daemon e portas
```

O passo a passo manual por sistema está em [REQUIREMENTS.md](REQUIREMENTS.md).

## Fluxo de trabalho

1. Crie uma branch a partir da `main` (`feat/...`, `fix/...`, `docs/...`).
2. Faça a mudança, com teste junto.
3. Rode localmente:

   ```bash
   make fmt        # ruff format + fix e TOC dos .md
   make lint       # ruff, TOC e conferência dos arquivos protegidos
   make tests      # unitários + integração + validador oficial (sobe e derruba a stack)
   ```

4. Se a mudança afeta o comportamento do validador, atualize a seção "Saída do validador" do [README.md](README.md) com a saída completa de `make validate`.
5. Commits curtos e no imperativo (`Add retry span attribute`). Abra o PR para a `main` descrevendo o que mudou e como foi testado.

## Convenções

| Item | Regra |
|---|---|
| Código, identificadores e comentários | inglês (en-US) |
| Documentação | português (pt-BR), em `docs/` e nos `.md` da raiz |
| Nomes do contrato (tools, campos JSON, mensagens de erro, skill `reservar-sala`) | exatamente como no [TASK.md](TASK.md) e em `exemplos/wire/` |
| Estilo Python | ruff (`line-length` 120); `make fmt` |
| Markdown | TOC no início entre dois `<!-- TOC -->` (gerado por `make toc`); diagramas Mermaid com analogias para iniciantes |
| Versão | só no arquivo `VERSION` |
| Segredos | nunca no código nem no git; `.env` fica fora do controle de versão |

## Arquivos que não podem mudar

`dados/`, `validador/` e `exemplos/` são do enunciado: o avaliador roda o validador a partir do repositório original. `make lint` e `make tests` param com erro se algum deles for alterado (`make check-protected`).

## Onde mexer

| Quero mudar... | Arquivo |
|---|---|
| uma regra de sala ou uma mensagem de erro | [servidor-mcp/src/mcp_server/domain.py](servidor-mcp/src/mcp_server/domain.py) |
| uma tool, o resource ou o MRTR | [servidor-mcp/src/mcp_server/server.py](servidor-mcp/src/mcp_server/server.py) |
| a ponte (pausa/retomada) | [agente/src/agent/bridge.py](agente/src/agent/bridge.py) |
| o protocolo A2A | [agente/src/agent/a2a_rpc.py](agente/src/agent/a2a_rpc.py), [agente/src/agent/card.py](agente/src/agent/card.py) |
| métricas e dashboards | `metrics.py` dos serviços e [scripts/gen_dashboards.py](scripts/gen_dashboards.py) (`make dashboards`) |
| a infraestrutura | [docker-compose.yml](docker-compose.yml), [observability/](observability/), [Makefile](Makefile) |

Mudou arquitetura, fluxo, estados, classes ou testes? Atualize o diagrama correspondente em [docs/](docs/README.md).
