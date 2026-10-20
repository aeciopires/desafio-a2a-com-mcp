<!-- TOC -->
- [Changelog](#changelog)
  - [Como versionar](#como-versionar)
  - [[Não lançado]](#não-lançado)
    - [Adicionado](#adicionado)
    - [Alterado](#alterado)
  - [[0.1.0] - 2026-10-18](#010---2026-10-18)
    - [Adicionado](#adicionado-1)
<!-- TOC -->

# Changelog

Todas as mudanças relevantes deste projeto são registradas neste arquivo.

O formato segue o [Keep a Changelog 1.1.0](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota o [Versionamento Semântico 2.0.0](https://semver.org/lang/pt-BR/). A versão atual fica no arquivo [VERSION](VERSION).

## Como versionar

Analogia: pense na versão como o endereço `MAIOR.MENOR.CORREÇÃO` de um prédio. Trocar a fachada inteira (algo que quebra quem já usava) muda o número **MAIOR**; abrir uma sala nova sem mexer nas antigas muda o **MENOR**; consertar uma lâmpada muda só a **CORREÇÃO**.

| Tipo de mudança | Exemplo neste projeto | Incrementa |
|---|---|---|
| Quebra de compatibilidade | mudar um contrato imutável do [CLAUDE.md](CLAUDE.md) (nome de tool, mensagem de erro, porta padrão, formato do wire) | MAIOR (`1.0.0` → `2.0.0`) |
| Funcionalidade nova compatível | novo dashboard, nova métrica, novo comando no Makefile, nova variável de ambiente opcional | MENOR (`0.1.0` → `0.2.0`) |
| Correção compatível | bug corrigido, documentação, atualização de dependência sem mudança de comportamento | CORREÇÃO (`0.1.0` → `0.1.1`) |

Enquanto a versão for `0.y.z`, o projeto está em desenvolvimento inicial e a API pública ainda pode mudar.

Categorias usadas em cada versão: **Adicionado**, **Alterado**, **Obsoleto**, **Removido**, **Corrigido** e **Segurança**.

## [Não lançado]

### Adicionado

- `CHANGELOG.md` seguindo Keep a Changelog e Versionamento Semântico, com a regra de manutenção no [CLAUDE.md](CLAUDE.md) e no [CONTRIBUTING.md](CONTRIBUTING.md).
- Tabela **Diferenças entre as versões** no [REQUIREMENTS-UBUNTU.md](REQUIREMENTS-UBUNTU.md), agora um guia único para Ubuntu 22.04, 24.04 e 26.04 (codinome, fim do suporte, `python3` do sistema e repositório do Docker).

### Alterado

- Grafana Loki atualizado de 3.6.18 para 3.7.8 e Grafana Alloy de 1.20.1 para 1.21.0, sem mudança na configuração.
- Imagens Docker (Dockerfiles e `docker-compose.yml`) fixadas só pela tag exata, sem o digest `@sha256`.
- Instalação manual do Docker no Ubuntu segue a documentação oficial atual: repositório em `/etc/apt/sources.list.d/docker.sources` (formato deb822) no lugar de `docker.list`.

## [0.1.0] - 2026-10-18

Primeira versão da ponte A2A com MCP por dentro, com o validador oficial em 36/36.

### Adicionado

- Servidor MCP (`servidor-mcp/`, porta `7301`, `/mcp`) em Streamable HTTP stateless, com as tools `listar_salas`, `consultar_disponibilidade` e `reservar_sala`, o resource `politica://uso` e o fluxo MRTR com `requestState` assinado.
- Agente (`agente/`, porta `7300`) que é host MCP por dentro e servidor A2A v1.0 por fora (`/a2a`, `/.well-known/agent-card.json`), com a skill `reservar-sala`, o artifact `reserva` e a tradução de `input_required` para `TASK_STATE_INPUT_REQUIRED`.
- Swagger/OpenAPI nos dois serviços.
- Observabilidade opcional: métricas Prometheus, traces OpenTelemetry no Jaeger, logs no Loki via Alloy e dashboards do Grafana gerados por `scripts/gen_dashboards.py`.
- `docker-compose.yml`, Dockerfiles com imagens base fixadas por digest e Makefile com os comandos de lint, testes, validação, TOC e verificação dos arquivos protegidos.
- Testes unitários, de integração e do fluxo do avaliador.
- Documentação em `docs/` (arquitetura, fluxos, estados, classes, testes, observabilidade, tracing, Swagger, variáveis, troubleshooting, glossário), REQUIREMENTS por sistema operacional, PLAN.md e CLAUDE.md.
- Arquivo `VERSION` como fonte única da versão.
- `CONTRIBUTING.md` com o fluxo de fork e pull request e licença MIT (`LICENSE`).

[Não lançado]: https://github.com/aeciopires/desafio-a2a-com-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aeciopires/desafio-a2a-com-mcp/releases/tag/v0.1.0
