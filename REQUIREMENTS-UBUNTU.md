<!-- TOC -->
- [Requisitos no Ubuntu (22.04, 24.04 e 26.04, amd64)](#requisitos-no-ubuntu-2204-2404-e-2604-amd64)
  - [1. Caminho automático](#1-caminho-automático)
  - [2. Instalação manual (fontes oficiais)](#2-instalação-manual-fontes-oficiais)
    - [Docker Engine, Compose v2 e buildx](#docker-engine-compose-v2-e-buildx)
    - [mise, Python e uv](#mise-python-e-uv)
    - [Python do sistema (para o validador)](#python-do-sistema-para-o-validador)
  - [3. Conferência final](#3-conferência-final)
<!-- TOC -->

# Requisitos no Ubuntu (22.04, 24.04 e 26.04, amd64)

## 1. Caminho automático

```bash
sudo apt-get update && sudo apt-get install -y make curl git   # pré-requisitos do Makefile
make check-os                # confirma Ubuntu suportado e amd64
make install                 # instala mise em ~/.local/bin (sem sudo), Python 3.14.8, uv e as dependências; cria .env
make check-dependencies      # confere Docker/Compose/buildx/daemon/portas e indica o que falta
```

Se `~/.local/bin` não estiver no `PATH`, ative o mise ([documentação oficial](https://mise.jdx.dev/getting-started.html#activate-mise)):

```bash
echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc && source ~/.bashrc
```

O Docker não é instalado por `make install`: siga o passo 2.

## 2. Instalação manual (fontes oficiais)

### Docker Engine, Compose v2 e buildx

Fonte: [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Confira lá se a sua versão do Ubuntu está na lista de suportadas (para a 26.04, verifique a disponibilidade do repositório oficial antes de instalar).

```bash
# Remove pacotes não oficiais que conflitam
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove -y $pkg; done

# Repositório oficial da Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# Engine + CLI + buildx + Compose v2
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run --rm hello-world
```

Para usar o Docker sem `sudo` ([pós-instalação no Linux](https://docs.docker.com/engine/install/linux-postinstall/)):

```bash
sudo usermod -aG docker "$USER"
newgrp docker    # ou faça logout/login
```

Para gerar imagens arm64 num host amd64 (`make build-multiarch`), habilite a emulação ([multi-platform builds](https://docs.docker.com/build/building/multi-platform/)):

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64
```

### mise, Python e uv

Fonte: [mise - Getting started](https://mise.jdx.dev/getting-started.html).

```bash
curl https://mise.run | sh                                   # instala em ~/.local/bin
echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc && source ~/.bashrc
cd desafio-a2a-com-mcp
mise trust && mise install                                   # Python e uv nas versões de mise.toml
for dir in servidor-mcp agente .; do (cd $dir && mise exec -- uv sync --frozen); done
make secret                                                  # cria .env com REQUEST_STATE_SECRET e GRAFANA_ADMIN_PASSWORD
```

Referência do uv: [Installing uv](https://docs.astral.sh/uv/getting-started/installation/). Aqui ele vem pelo mise, não precisa instalar à parte.

### Python do sistema (para o validador)

O Ubuntu 22.04+ já traz Python 3.10+, suficiente para `python3 validador/validar.py`. Se não estiver instalado: `sudo apt-get install -y python3`.

## 3. Conferência final

```bash
make check-dependencies
make up && make validate
```
