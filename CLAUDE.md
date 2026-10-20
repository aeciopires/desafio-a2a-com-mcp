<!-- TOC -->
- [CLAUDE.md](#claudemd)
  - [Fontes de verdade](#fontes-de-verdade)
  - [Proibições (não negociáveis)](#proibições-não-negociáveis)
  - [Contratos imutáveis](#contratos-imutáveis)
  - [Idiomas](#idiomas)
  - [Markdown: TOC obrigatório](#markdown-toc-obrigatório)
  - [Documentação com diagramas e analogias](#documentação-com-diagramas-e-analogias)
  - [Versão](#versão)
  - [Changelog](#changelog)
  - [Atualização de dependências (só quando pedido explicitamente)](#atualização-de-dependências-só-quando-pedido-explicitamente)
  - [Observabilidade (extra, não pode quebrar o desafio)](#observabilidade-extra-não-pode-quebrar-o-desafio)
  - [Erros que ajudam a achar a causa raiz](#erros-que-ajudam-a-achar-a-causa-raiz)
  - [Definição de pronto](#definição-de-pronto)
<!-- TOC -->

# CLAUDE.md

Instruções e guardrails para manter este repositório consistente com o [TASK.md](TASK.md) (o enunciado do desafio "A Ponte: um agente A2A com MCP por dentro").

## Fontes de verdade

1. [TASK.md](TASK.md): requisitos, mensagens exatas, critérios de aceite e pedidos adicionais.
2. [exemplos/wire/](exemplos/wire/): forma exata dos requests e responses. Em caso de dúvida sobre o formato, o wire vence.
3. [validador/validar.py](validador/validar.py): as 36 verificações que o avaliador roda. A entrega só está pronta com 36/36 e código de saída 0.
4. [PLAN.md](PLAN.md): plano de implementação. Atualize-o quando uma decisão mudar.

## Proibições (não negociáveis)

- **Não alterar `dados/`, `validador/` nem `exemplos/`**, nem por formatação automática. O ruff da raiz exclui essas pastas; confira com `make check-protected` (roda em `make lint` e `make tests`). Se algo mudou: `git checkout -- dados validador exemplos`.
- Nada de LLM no caminho de execução, nem SDK de provedor de LLM nos `pyproject.toml`. O agente é determinístico.
- Nenhum segredo versionado. `.env` fica fora do git; `.env.example` só tem nomes. `REQUEST_STATE_SECRET` vem só do ambiente.
- O agente não implementa regra de sala (conflito, política, alternativas são do servidor MCP). Ele traduz protocolo.
- O agente não abre, não interpreta e não reconstrói o `requestState`: guarda e ecoa byte a byte. O valor nunca vai para respostas A2A, logs ou spans.
- Sem sessão de protocolo: cada request MCP leva `_meta` completo. Nada pode ser inferido de requests anteriores.
- Dois processos separados que falam HTTP. Não importar código de um no outro.
- Não reescrever o protocolo para contornar o SDK. Se houver uma limitação real, documente no README com a evidência (como já feito para o cliente MCP e o `a2a-sdk`).

## Contratos imutáveis

- Mensagens de erro exatas (em [domain.py](servidor-mcp/src/mcp_server/domain.py)): `Sala inexistente: <id>`, `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`, `Duracao acima do limite: a politica permite no maximo 2 horas`, `Intervalo invalido: fim deve ser posterior a inicio`, `Sem alternativas disponiveis no intervalo`.
- Linha da pausa: exatamente `alternativas: <ids separados por virgula e espaco>`, na ordem do `enum`.
- Códigos: `-32602` (+HTTP 400 para `_meta` incompleto), `-32021` (+HTTP 400, `data.requiredCapabilities`), `-32020` (headers divergentes).
- Nomes: tools `listar_salas`, `consultar_disponibilidade`, `reservar_sala`; resource `politica://uso`; skill `reservar-sala`; artifact `reserva`.
- Portas padrão: agente `7300` (`/a2a`, `/.well-known/agent-card.json`), MCP `7301` (`/mcp`). Elas são parametrizáveis por variável de ambiente, mas os padrões não mudam.
- Capability declarada pelo agente: exatamente `{"elicitation": {"form": {}}}`.
- O retry MCP usa sempre um id JSON-RPC novo.

## Idiomas

- Código, identificadores, comentários, mensagens de log e erros técnicos: **inglês (en-US)**.
- Documentação (`README.md`, `docs/`, `REQUIREMENTS*.md`, `CONTRIBUTING.md`, este arquivo): **português (pt-BR)**.
- Exceção: nomes do contrato acima, que seguem o enunciado.

## Markdown: TOC obrigatório

- Todo `.md` novo ou alterado tem TOC **no início do arquivo**, entre **duas** linhas `<!-- TOC -->` (abertura e fechamento iguais; não use `<!-- /TOC -->`, que conflita com plugins de editor).
- O TOC lista todos os níveis, **incluindo o `#`**, aninhados como no plugin Markdown All in One, com âncoras no padrão do GitHub.
- Gere com `make toc` ([scripts/toc.py](scripts/toc.py)): é idempotente (rodar duas vezes não muda nada) e ignora `dados/`, `validador/`, `exemplos/` e `TASK.md`. `make lint` falha se algum TOC estiver desatualizado.

## Documentação com diagramas e analogias

- Ao mudar arquitetura, fluxos (API, agentes, MRTR), estados da Task, classes, testes ou observabilidade, **atualize o diagrama Mermaid correspondente** em [docs/](docs/README.md) na mesma mudança.
- Cada documento de `docs/` tem pelo menos uma **analogia para iniciantes** (recepção do prédio, garçom, envelope lacrado, senha de atendimento, código de rastreio...). Mantenha-as coerentes com o código.
- O README tem links com número de linha para a ponte (`bridge.py`, `mcp_host.py`, `server.py`, `tasks.py`). Se essas linhas mudarem, atualize os links.
- O README precisa manter as quatro seções exigidas: **Como rodar**, **Onde a ponte acontece**, **Decisões técnicas** e **Saída do validador** (saída completa da última execução de `make validate`).

## Versão

- `VERSION` é a fonte única (hoje `0.1.0`). É lida pelo Python (`config.get_version()`), pelo Makefile (`make version`) e pelas tags das imagens. Nenhum outro arquivo fixa a versão (os `pyproject.toml` usam `dynamic = ["version"]`).
- A versão segue o [Versionamento Semântico 2.0.0](https://semver.org/lang/pt-BR/) (`MAIOR.MENOR.CORREÇÃO`): **MAIOR** quando um contrato imutável acima muda (quebra compatibilidade), **MENOR** para funcionalidade nova compatível, **CORREÇÃO** para correções, docs e atualizações sem mudança de comportamento.

## Changelog

- Toda mudança relevante (código, configuração, dependências, docs que mudam o uso) entra no [CHANGELOG.md](CHANGELOG.md), **na mesma mudança**, na seção `[Não lançado]`, sob a categoria certa: **Adicionado**, **Alterado**, **Obsoleto**, **Removido**, **Corrigido** ou **Segurança** (formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)).
- Escreva do ponto de vista de quem usa o projeto, em pt-BR, uma linha por mudança. Não liste refatorações internas sem efeito visível.
- Ao lançar uma versão: escolha o incremento pelo SemVer, atualize o `VERSION`, renomeie `[Não lançado]` para `[X.Y.Z] - AAAA-MM-DD`, crie uma nova seção `[Não lançado]` vazia, atualize os links de comparação no fim do arquivo e a versão citada no README e neste arquivo. A tag git é `vX.Y.Z`.
- Nunca reescreva entradas de versões já lançadas; correções vão na próxima versão.

## Atualização de dependências (só quando pedido explicitamente)

Não atualize versões por iniciativa própria. Quando alguém pedir explicitamente para "atualizar as dependências/softwares para as versões mais recentes":

1. Consulte só fontes oficiais (PyPI, Docker Hub/GHCR, páginas de release dos projetos, documentação oficial).
2. Atualize, mantendo tudo travado:
   - [mise.toml](mise.toml): `python` e `uv`;
   - `servidor-mcp/pyproject.toml`, `agente/pyproject.toml` e o `pyproject.toml` da raiz (pins `==`), depois `uv lock` em cada um. Os pacotes `opentelemetry-*` andam sempre juntos, na mesma versão. Mantenha `mcp` alinhado à revisão `2026-07-28` da spec;
   - imagens base dos Dockerfiles (`python:<versão>-slim-<distro>` e `ghcr.io/astral-sh/uv`), só pela tag exata (sem digest `@sha256`; confira que a tag existe para amd64 e arm64 com `docker buildx imagetools inspect <imagem>`);
   - imagens do [docker-compose.yml](docker-compose.yml): Prometheus, Grafana, Jaeger, Loki e Alloy, só pela tag exata (nunca `latest`), sem digest. Leia as notas de versão (seções *breaking changes*) e confira [loki.yaml](observability/loki/loki.yaml) e [config.alloy](observability/alloy/config.alloy). **Jaeger:** o Grafana o lê via `/api/v3` (toggle `jaegerEnableGrpcEndpoint`); rode `test_grafana_reads_jaeger_v2_through_api_v3` e o dashboard 24836 (métricas `otelcol_*` em `:8888`) para confirmar que nada quebrou;
   - `SWAGGER_UI_VERSION` em `servidor-mcp/src/mcp_server/openapi.py` e `agente/src/agent/openapi.py`;
   - versões de Ubuntu/macOS suportadas em [scripts/check_os.sh](scripts/check_os.sh), se houver nova LTS.
3. Atualize os **REQUIREMENTS**: [REQUIREMENTS.md](REQUIREMENTS.md), [REQUIREMENTS-UBUNTU.md](REQUIREMENTS-UBUNTU.md) e [REQUIREMENTS-MACOS.md](REQUIREMENTS-MACOS.md). Revise os comandos e links de instalação conforme a documentação oficial atual (Docker Engine, Compose, buildx, Colima, Homebrew, mise, uv) e as versões citadas. O REQUIREMENTS-UBUNTU.md é um guia único para todas as versões suportadas: mantenha a tabela **Diferenças entre as versões** (codinome, fim do suporte, `python3` do sistema, repositório do Docker) e os avisos por versão.
4. Confira as configurações que dependem das versões: provisionamento do Grafana, [loki.yaml](observability/loki/loki.yaml), [config.alloy](observability/alloy/config.alloy) e [prometheus.yml](observability/prometheus/prometheus.yml).
5. Atualize [docs/decisoes-tecnicas.md](docs/decisoes-tecnicas.md) e o PLAN.md, se mudou alguma decisão.
6. Rode `make lint`, `make tests` e `make validate`. Cole a saída nova do validador no README.

## Observabilidade (extra, não pode quebrar o desafio)

- O log no stderr do servidor MCP (método, id e `traceparent` de cada request) é **obrigatório** e continua existindo mesmo com o OpenTelemetry ligado.
- O sistema tem que funcionar com Jaeger, Loki e Alloy parados (há teste de integração para isso).
- **Correlação:** o nome do serviço é o mesmo no `job` do Prometheus, no `service.name` do OTel e no label `service` do Loki (`agent`, `mcp-server`). Os UIDs dos datasources do Grafana são fixos (`prometheus`, `jaeger`, `loki`), e toda linha de log JSON leva `trace_id` e `span_id`. Se mudar um desses nomes, atualize provisionamento, dashboards, testes e docs juntos.
- Dashboards: edite [scripts/gen_dashboards.py](scripts/gen_dashboards.py) e rode `make dashboards`; não edite os JSON à mão.
- Não use auto-instrumentação do `httpx` no agente: o único `traceparent` enviado ao MCP é o do `_meta`.

## Erros que ajudam a achar a causa raiz

Toda falha de configuração ou de dependência deve dizer **o que** falhou, **por quê** e **como corrigir** (variável a definir, comando a rodar, URL oficial). Siga o padrão existente em `config.py`, `__main__.py` (porta ocupada) e `scripts/*.sh`. Erros novos entram em [docs/troubleshooting.md](docs/troubleshooting.md).

## Definição de pronto

- [ ] `make lint` sem erros (inclui TOC e arquivos protegidos).
- [ ] `make tests` verde (unitários, integração e validador), com a stack subindo e descendo sozinha.
- [ ] `make validate` com 36/36 e saída colada no README.
- [ ] Docs, diagramas e analogias atualizados; README com as quatro seções.
- [ ] [CHANGELOG.md](CHANGELOG.md) atualizado na seção `[Não lançado]`.
- [ ] Nenhum segredo, nenhuma dependência de LLM, nenhuma alteração em `dados/`, `validador/` ou `exemplos/`.
