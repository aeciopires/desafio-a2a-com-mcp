# syntax=docker/dockerfile:1
# Build context: repository root (VERSION and dados/ live there).
#   docker build -f servidor-mcp/Dockerfile --build-arg VERSION=$(cat VERSION) .
ARG PYTHON_IMAGE=python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY servidor-mcp/pyproject.toml servidor-mcp/uv.lock servidor-mcp/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3

FROM ${PYTHON_IMAGE}
ARG VERSION=0.0.0
LABEL org.opencontainers.image.title="Central de Salas MCP server" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/aeciopires/desafio-a2a-com-mcp"
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /opt/venv /opt/venv
COPY VERSION /app/VERSION
COPY servidor-mcp/src /app/src
# Seed data baked in for standalone runs; docker-compose also mounts ./dados read-only.
COPY dados /app/dados
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    VERSION_FILE=/app/VERSION \
    DATA_DIR=/app/dados \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=7301
WORKDIR /app
USER app
EXPOSE 7301
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['MCP_PORT']}/healthz\", timeout=2)"]
CMD ["python", "-m", "mcp_server"]
