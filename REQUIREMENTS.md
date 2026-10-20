<!-- TOC -->
- [Requisitos](#requisitos)
  - [Resumo do que é necessário](#resumo-do-que-é-necessário)
  - [Caminho automático (todos os sistemas)](#caminho-automático-todos-os-sistemas)
<!-- TOC -->

# Requisitos

Os requisitos dependem do sistema operacional. Descubra se o seu é suportado:

```bash
make check-os
```

| Sistema | Arquitetura | Guia |
|---|---|---|
| Ubuntu 22.04, 24.04 e 26.04 | amd64 (x86_64) | [REQUIREMENTS-UBUNTU.md](REQUIREMENTS-UBUNTU.md) (guia único, com as diferenças entre as versões) |
| macOS | amd64 (Intel) e arm64 (Apple Silicon) | [REQUIREMENTS-MACOS.md](REQUIREMENTS-MACOS.md) (Colima no lugar do Docker Desktop) |

Qualquer outro sistema ou arquitetura é recusado por `make check-os`, com a indicação deste arquivo.

## Resumo do que é necessário

| Ferramenta | Quem instala | Para quê |
|---|---|---|
| `make`, `curl`, `git` | sistema operacional | Makefile e instaladores |
| Docker Engine + Compose v2 + buildx | sistema operacional (Colima no macOS) | subir a stack e gerar imagens |
| [mise](https://mise.jdx.dev) | `make install` (no diretório do usuário, sem sudo) | gerenciar Python e uv do projeto |
| Python 3.14.8 e uv 0.13.1 | `make install` (via mise, versões em [mise.toml](mise.toml)) | rodar serviços, testes e validador |
| Python 3.10+ no sistema | sistema operacional (opcional) | rodar `python3 validador/validar.py` fora do mise |

## Caminho automático (todos os sistemas)

```bash
make check-os            # 1. sistema suportado?
make install             # 2. mise + Python + uv + dependências + .env (não instala Docker)
make check-dependencies  # 3. confere tudo (Docker, Compose, buildx, daemon, portas) e mostra a URL oficial do que faltar
```

O Docker não é instalado pelo Makefile: siga o guia do seu sistema.
