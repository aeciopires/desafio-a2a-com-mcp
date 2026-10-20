# syntax=docker/dockerfile:1
# Build context: repository root (VERSION and dados/ live there).
#   docker build -f agente/Dockerfile --build-arg VERSION=$(cat VERSION) .
ARG PYTHON_IMAGE=python:3.14.8-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY agente/pyproject.toml agente/uv.lock agente/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3

FROM ${PYTHON_IMAGE}
ARG VERSION=0.0.0
LABEL org.opencontainers.image.title="Central de Salas A2A agent" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/aeciopires/desafio-a2a-com-mcp"
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /opt/venv /opt/venv
COPY VERSION /app/VERSION
COPY agente/src /app/src
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    VERSION_FILE=/app/VERSION \
    AGENT_HOST=0.0.0.0 \
    AGENT_PORT=7300
WORKDIR /app
USER app
EXPOSE 7300
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['AGENT_PORT']}/healthz\", timeout=2)"]
CMD ["python", "-m", "agent"]
