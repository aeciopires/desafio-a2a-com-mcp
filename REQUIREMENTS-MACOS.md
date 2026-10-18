<!-- TOC -->
- [Requisitos no macOS (amd64 e arm64)](#requisitos-no-macos-amd64-e-arm64)
  - [1. Caminho automático](#1-caminho-automático)
  - [2. Instalação manual (fontes oficiais)](#2-instalação-manual-fontes-oficiais)
    - [Homebrew](#homebrew)
    - [Colima, CLI do Docker, Compose v2 e buildx](#colima-cli-do-docker-compose-v2-e-buildx)
    - [mise, Python e uv](#mise-python-e-uv)
    - [Python para o validador](#python-para-o-validador)
  - [3. Conferência final](#3-conferência-final)
<!-- TOC -->

# Requisitos no macOS (amd64 e arm64)

No macOS os containers rodam numa VM Linux do **[Colima](https://github.com/abiosoft/colima)**; o Docker Desktop não é usado. As imagens do projeto são multi-arch (`linux/amd64` e `linux/arm64`), então funcionam tanto em Macs Intel quanto Apple Silicon.

## 1. Caminho automático

```bash
xcode-select --install       # make, git e curl (Command Line Tools)
make check-os                # confirma macOS e arquitetura (x86_64 ou arm64)
make install                 # instala mise em ~/.local/bin (sem sudo), Python 3.14.8, uv e as dependências; cria .env
make check-dependencies      # confere Colima/Docker/Compose/buildx/daemon/portas e indica o que falta
```

Ative o mise no shell ([documentação oficial](https://mise.jdx.dev/getting-started.html#activate-mise)):

```bash
echo 'eval "$(~/.local/bin/mise activate zsh)"' >> ~/.zshrc && source ~/.zshrc
```

O Colima e a CLI do Docker não são instalados por `make install`: siga o passo 2.

## 2. Instalação manual (fontes oficiais)

### Homebrew

Fonte: [brew.sh](https://brew.sh).

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Colima, CLI do Docker, Compose v2 e buildx

Fontes: [Colima - Installation](https://github.com/abiosoft/colima#installation), fórmulas [docker](https://formulae.brew.sh/formula/docker), [docker-compose](https://formulae.brew.sh/formula/docker-compose) e [docker-buildx](https://formulae.brew.sh/formula/docker-buildx).

```bash
brew install colima docker docker-compose docker-buildx
```

Para a CLI do Docker encontrar os plugins `compose` e `buildx` instalados pelo Homebrew, siga o aviso das fórmulas e registre o diretório de plugins em `~/.docker/config.json`:

```bash
mkdir -p ~/.docker
cat > ~/.docker/config.json <<EOF
{
  "cliPluginsExtraDirs": ["$(brew --prefix)/lib/docker/cli-plugins"]
}
EOF
docker compose version && docker buildx version
```

(Se o `~/.docker/config.json` já existir, só acrescente a chave `cliPluginsExtraDirs`.)

Inicie a VM, que precisa estar rodando sempre que for usar o projeto:

```bash
colima start --cpu 2 --memory 4
docker run --rm hello-world
```

Em Apple Silicon, a VM é arm64 e as imagens arm64 rodam nativamente. Para gerar imagens amd64 também (`make build-multiarch`), habilite a emulação dentro da VM ([multi-platform builds](https://docs.docker.com/build/building/multi-platform/)):

```bash
docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64
```

O Colima monta o socket do Docker como `unix:///var/run/docker.sock` dentro da VM, e é esse socket que o Grafana Alloy usa para ler os logs dos containers. Não é preciso configurar nada a mais.

### mise, Python e uv

Fonte: [mise - Getting started](https://mise.jdx.dev/getting-started.html) (alternativa: `brew install mise`).

```bash
curl https://mise.run | sh
echo 'eval "$(~/.local/bin/mise activate zsh)"' >> ~/.zshrc && source ~/.zshrc
cd desafio-a2a-com-mcp
mise trust && mise install
for dir in servidor-mcp agente .; do (cd $dir && mise exec -- uv sync --frozen); done
make secret
```

### Python para o validador

O `python3` das Command Line Tools da Apple é 3.9, e o validador exige 3.10+. Use `make validate` (que usa o Python do mise) ou:

```bash
mise exec -- python validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

## 3. Conferência final

```bash
make check-dependencies
make up && make validate
```
