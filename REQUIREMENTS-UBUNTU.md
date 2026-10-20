<!-- TOC -->
- [Requisitos no Ubuntu (22.04, 24.04 e 26.04, amd64)](#requisitos-no-ubuntu-2204-2404-e-2604-amd64)
  - [Diferenças entre as versões](#diferenças-entre-as-versões)
  - [1. Caminho automático](#1-caminho-automático)
  - [2. Instalação manual (fontes oficiais)](#2-instalação-manual-fontes-oficiais)
    - [Docker Engine, Compose v2 e buildx](#docker-engine-compose-v2-e-buildx)
    - [mise, Python e uv](#mise-python-e-uv)
    - [Python do sistema (para o validador)](#python-do-sistema-para-o-validador)
  - [3. Conferência final](#3-conferência-final)
<!-- TOC -->

# Requisitos no Ubuntu (22.04, 24.04 e 26.04, amd64)

Um único guia para as três versões LTS suportadas. Os passos são os mesmos; o que muda de uma versão para outra está na tabela abaixo e nos avisos **[22.04]**, **[24.04]** e **[26.04]** ao longo do texto.

## Diferenças entre as versões

| Item | 22.04 LTS | 24.04 LTS | 26.04 LTS |
|---|---|---|---|
| Codinome (`UBUNTU_CODENAME`) | `jammy` | `noble` | `resolute` |
| Suporte padrão da Canonical até | abril de 2027 | abril de 2029 | abril de 2031 |
| `python3` do sistema (para o validador) | 3.10 | 3.12 | 3.14 |
| Repositório oficial do Docker (`download.docker.com`) | disponível | disponível | disponível |
| Python e uv do projeto | 3.14.8 e 0.13.1 via mise (iguais nas três) | idem | idem |

O que isso significa na prática:

- **[22.04]** O `python3` do sistema é o 3.10, a versão mínima que o validador aceita. Funciona, mas é a versão mais próxima do limite. A 22.04 sai do suporte padrão em abril de 2027; prefira a 24.04 ou a 26.04 em máquinas novas.
- **[24.04]** Nada específico: todos os passos funcionam como estão.
- **[26.04]** O `python3` do sistema já é o 3.14, o mesmo ramo que o projeto usa. Mesmo assim, os serviços rodam com o Python do mise (3.14.8), para todo mundo usar a mesma versão.
- **Em todas:** o codinome é lido de `/etc/os-release` no passo do Docker, então o mesmo comando serve para as três versões. O projeto não usa o Python do sistema para rodar os serviços, só (opcionalmente) para `python3 validador/validar.py`.

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

Fonte: [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/). As três versões (Jammy 22.04, Noble 24.04 e Resolute 26.04) estão na lista de suportadas, e os comandos abaixo são os mesmos para todas.

```bash
# Remove pacotes não oficiais que conflitam (o apt pode dizer que nenhum está instalado)
sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc | cut -f1)

# Chave GPG do repositório oficial da Docker
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Repositório (o codinome jammy/noble/resolute vem de /etc/os-release)
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update

# Engine + CLI + buildx + Compose v2
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run --rm hello-world
```

Se você já tinha o repositório configurado pelo formato antigo (`/etc/apt/sources.list.d/docker.list`), apague esse arquivo antes, para o apt não reclamar de fonte duplicada: `sudo rm -f /etc/apt/sources.list.d/docker.list`.

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

Fonte: [mise - Getting started](https://mise.jdx.dev/getting-started.html). Igual nas três versões.

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

O validador (`python3 validador/validar.py`) precisa de Python 3.10 ou mais novo, e as três versões já trazem um `python3` compatível (veja a [tabela](#diferenças-entre-as-versões)). Se não estiver instalado: `sudo apt install -y python3`. Se preferir não depender dele, `make validate` roda o validador com o Python do mise.

## 3. Conferência final

```bash
make check-dependencies
make up && make validate
```
