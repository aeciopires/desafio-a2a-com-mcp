<!-- TOC -->
- [Como contribuir](#como-contribuir)
  - [Preparar o ambiente](#preparar-o-ambiente)
  - [2. Fluxo de commits e pull requests](#2-fluxo-de-commits-e-pull-requests)
  - [Convenções](#convenções)
  - [Arquivos que não podem mudar](#arquivos-que-não-podem-mudar)
  - [Onde mexer](#onde-mexer)
<!-- TOC -->

# Como contribuir

Obrigado por contribuir! Este guia é para pessoas. Agentes seguem o [CLAUDE.md](CLAUDE.md), que tem as mesmas regras com mais detalhes.

## Preparar o ambiente

1. Leia [REQUIREMENTS.md](REQUIREMENTS.md). Ele indica o arquivo de requisitos do seu sistema.
2. Rode as checagens e instalação:

```bash
make check-os              # sistema suportado? (Ubuntu 22.04/24.04/26.04 amd64, macOS amd64/arm64)
make check-dependencies    # Docker, Compose, buildx, daemon e portas
make install               # mise, Python, uv, dependências e .env
```

3. Configure o ambiente:

```bash
cp .env.example .env # Preencha as variáveis de ambiente
```

4. Suba e teste a stack:

```bash
make fmt   # ruff format + fix e TOC dos .md
make lint  # ruff, TOC e conferência dos arquivos protegidos
make tests # unitários + integração + validador oficial (sobe e derruba a stack)
```

## 2. Fluxo de commits e pull requests

Use um fork para propor alterações. Configure a autenticação SSH do GitHub
conforme a [documentação oficial](https://docs.github.com/authentication/connecting-to-github-with-ssh)
e siga estes passos:

1. Crie um fork de `aeciopires/desafio-a2a-com-mcp` no GitHub e clone-o:

```bash
git clone git@github.com:SEU_USUARIO/desafio-a2a-com-mcp.git
cd desafio-a2a-com-mcp
```

2. Registre o repositório original como `upstream` e confira os remotos:

```bash
git remote add upstream git@github.com:aeciopires/desafio-a2a-com-mcp.git
git remote -v
```

3. Atualize a branch principal local e crie uma branch para sua alteração:

```bash
git switch main
git pull upstream main
git switch -c tipo/descricao-curta
```

   Use um nome simples e descritivo para a branch, por exemplo
   `docs/guia-de-instalacao` ou `fix/carregamento-agente`.

4. Faça e valide as alterações. Revise o diff e confirme que somente os arquivos
   pretendidos serão incluídos:

```bash
git status --short
git diff --check
git diff
```

5. Adicione os arquivos pertinentes, crie commits focados com mensagens
   descritivas e envie a branch ao seu fork:

```bash
git add caminho/do/arquivo
git commit -m "docs: descreve a estrutura do projeto"
git push --set-upstream origin tipo/descricao-curta
```

   Não inclua credenciais, arquivos `.env`, ambientes virtuais nem outros
   arquivos locais no commit. Se houver mais de uma alteração independente,
   prefira separá-las em commits claros.

6. No GitHub, abra um pull request do seu fork para a branch `main` do
   repositório original. Descreva o objetivo, resuma as mudanças e informe as
   validações executadas. Considere e responda às sugestões da revisão; envie
   novos commits à mesma branch quando fizer ajustes.

7. Após o merge, atualize sua branch principal e, se desejar, remova a branch de
   trabalho:

```bash
git switch main
git pull upstream main
git push origin main
git branch -d tipo/descricao-curta
git push origin --delete tipo/descricao-curta
```

Para sincronizar o fork posteriormente, estando na branch `main`, execute:

```bash
git pull upstream main
git push origin main
```

Contribuições estão sujeitas aos termos da licença MIT deste repositório.

## Convenções

| Item | Regra |
|---|---|
| Código, identificadores e comentários | inglês (en-US) |
| Documentação | português (pt-BR), em `docs/` e nos `.md` da raiz |
| Nomes do contrato (tools, campos JSON, mensagens de erro, skill `reservar-sala`) | exatamente como no [TASK.md](TASK.md) e em `exemplos/wire/` |
| Estilo Python | ruff (`line-length` 120); `make fmt` |
| Markdown | TOC no início entre dois `<!-- TOC -->` (gerado por `make toc`); diagramas Mermaid com analogias para iniciantes |
| Versão | só no arquivo `VERSION`, seguindo o [Versionamento Semântico](https://semver.org/lang/pt-BR/) |
| Changelog | toda mudança relevante entra em `[Não lançado]` no [CHANGELOG.md](CHANGELOG.md), no mesmo pull request |
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
