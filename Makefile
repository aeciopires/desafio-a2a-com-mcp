# Central de Salas - A2A agent with an MCP server inside.
# Run `make help` for the list of targets. Supported OS: Ubuntu 22.04/24.04/26.04 (amd64), macOS (amd64/arm64).

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

VERSION := $(shell cat VERSION 2>/dev/null || echo 0.0.0)
export VERSION

MISE ?= $(shell command -v mise 2>/dev/null || echo $(HOME)/.local/bin/mise)
UV := $(MISE) exec -- uv
PYTHON := $(MISE) exec -- python
# The validator needs Python >= 3.10 (macOS ships 3.9): prefer the mise one.
VALIDATOR_PYTHON := $(shell [ -x "$(MISE)" ] && echo "$(MISE) exec -- python" || echo python3)
COMPOSE := docker compose
PLATFORMS ?= linux/amd64,linux/arm64
REGISTRY ?= desafio-a2a
BUILDER ?= desafio-a2a-builder

# Ports and URLs (overridable through .env or the environment).
ENV_VAL = $(or $(shell grep -E '^$(1)=' .env 2>/dev/null | tail -1 | cut -d= -f2-),$(2))
AGENT_PORT ?= $(call ENV_VAL,AGENT_PORT,7300)
MCP_PORT ?= $(call ENV_VAL,MCP_PORT,7301)
GRAFANA_PORT ?= $(call ENV_VAL,GRAFANA_PORT,3000)
PROMETHEUS_PORT ?= $(call ENV_VAL,PROMETHEUS_PORT,9090)
JAEGER_UI_PORT ?= $(call ENV_VAL,JAEGER_UI_PORT,16686)
LOKI_PORT ?= $(call ENV_VAL,LOKI_PORT,3100)
ALLOY_UI_PORT ?= $(call ENV_VAL,ALLOY_UI_PORT,12345)
AGENT_URL := http://localhost:$(AGENT_PORT)
MCP_URL := http://localhost:$(MCP_PORT)

# Run a command with the stack up and always bring it down afterwards, keeping the exit code.
define with_stack
	@$(MAKE) --no-print-directory up
	@rc=0; $(1) || rc=$$?; \
	$(MAKE) --no-print-directory down; \
	if [ $$rc -eq 0 ]; then echo -e "\n\033[32m[ ok ] $(2): PASSED\033[0m"; \
	else echo -e "\n\033[31m[fail] $(2): FAILED (exit $$rc). Logs: re-run with the stack up (make up) and use make logs.\033[0m"; fi; \
	exit $$rc
endef

##@ Help
.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Central de Salas %s\n\nUsage: make \033[36m<target>\033[0m\n", "$(VERSION)"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

.PHONY: version
version: ## Print the project version (from the VERSION file)
	@echo $(VERSION)

##@ Environment
.PHONY: check-os
check-os: ## Check that the OS and architecture are supported
	@./scripts/check_os.sh

.PHONY: check-ports
check-ports: ## Check that every published host port is free
	@./scripts/check_ports.sh --skip-own

.PHONY: check-dependencies
check-dependencies: check-os ## Check mise, Python, uv, Docker, Compose, buildx, daemon and ports
	@./scripts/check_deps.sh

.PHONY: install
install: check-os ## Install mise (user dir, no sudo) and the project dependencies, create .env
	@if [ ! -x "$(MISE)" ]; then \
		echo "[info] Installing mise into $$HOME/.local/bin (official installer: https://mise.run)"; \
		curl -fsSL https://mise.run | sh || { echo "[fail] mise install failed. Manual steps: https://mise.jdx.dev/getting-started.html"; exit 1; }; \
	fi
	@$(MISE) trust --quiet mise.toml
	@echo "[info] Installing tools pinned in mise.toml (python, uv)..."
	@$(MISE) install
	@for dir in servidor-mcp agente .; do \
		echo "[info] uv sync in $$dir"; \
		(cd $$dir && $(UV) sync --frozen) || { echo "[fail] uv sync failed in $$dir. Try: rm -rf $$dir/.venv && make install"; exit 1; }; \
	done
	@./scripts/gen_secret.sh
	@echo -e "\n[ ok ] Installed. Docker/Compose are not installed by this target: see REQUIREMENTS.md, then run make check-dependencies."
	@if ! echo ":$$PATH:" | grep -q ":$$HOME/.local/bin:"; then echo "[warn] Add ~/.local/bin to PATH (and see https://mise.jdx.dev/getting-started.html#activate-mise)"; fi

.PHONY: secret
secret: ## Create .env if needed and generate REQUEST_STATE_SECRET / GRAFANA_ADMIN_PASSWORD when empty
	@./scripts/gen_secret.sh

##@ Docker
.PHONY: check-docker
check-docker:
	@docker info >/dev/null 2>&1 || { \
		echo "[fail] Docker daemon is not reachable."; \
		if [ "$$(uname -s)" = "Darwin" ]; then echo "  -> start Colima: colima start --cpu 2 --memory 4"; \
		else echo "  -> start it: sudo systemctl start docker (permission denied? https://docs.docker.com/engine/install/linux-postinstall/)"; fi; \
		exit 1; }
	@[ -f .env ] || { echo "[fail] .env not found. Run: make secret (or make install)"; exit 1; }

.PHONY: build
build: check-os check-docker ## Build the images for the native platform, tagged with VERSION
	@echo "[info] Building desafio-a2a/mcp-server:$(VERSION) and desafio-a2a/agent:$(VERSION)"
	@$(COMPOSE) build mcp-server agent

.PHONY: build-multiarch
build-multiarch: check-os check-docker ## Build linux/amd64+arm64 images (OCI tars in dist/; PUSH=1 REGISTRY=... to push)
	@docker buildx inspect $(BUILDER) >/dev/null 2>&1 || docker buildx create --name $(BUILDER) --driver docker-container >/dev/null
	@docker buildx inspect --bootstrap $(BUILDER) | grep -q "linux/arm64" || { \
		echo "[fail] Builder $(BUILDER) cannot build linux/arm64. Enable QEMU emulation:"; \
		echo "  docker run --privileged --rm tonistiigi/binfmt --install arm64   (https://docs.docker.com/build/building/multi-platform/)"; \
		exit 1; }
	@mkdir -p dist
	@for svc in mcp-server:servidor-mcp agent:agente; do \
		name=$${svc%%:*}; dir=$${svc##*:}; tag=$(REGISTRY)/$$name:$(VERSION); \
		if [ "$${PUSH:-0}" = "1" ]; then out="--push"; else out="--output type=oci,dest=dist/$$name-$(VERSION).oci.tar"; fi; \
		echo "[info] $$tag for $(PLATFORMS)"; \
		docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) -f $$dir/Dockerfile \
			--build-arg VERSION=$(VERSION) -t $$tag $$out . ; \
	done
	@echo "[ ok ] Multi-arch images built ($(PLATFORMS))."

.PHONY: up
up: check-os check-docker ## Start the whole stack (agent, MCP server, Prometheus, Grafana, Jaeger, Loki, Alloy)
	@./scripts/check_ports.sh --skip-own
	@$(COMPOSE) up -d --build --wait --wait-timeout 180 || { \
		echo "[fail] The stack did not become healthy. Check: make logs   (or docker compose ps)"; exit 1; }
	@$(MAKE) --no-print-directory urls

.PHONY: urls
urls: ## Print the URLs of every service
	@echo ""
	@echo "  Agent (A2A)      $(AGENT_URL)/a2a   card: $(AGENT_URL)/.well-known/agent-card.json"
	@echo "  Agent Swagger    $(AGENT_URL)/docs"
	@echo "  MCP server       $(MCP_URL)/mcp   Swagger: $(MCP_URL)/docs"
	@echo "  Grafana          http://localhost:$(GRAFANA_PORT)   (user: admin unless GRAFANA_ADMIN_USER; password in .env)"
	@echo "  Prometheus       http://localhost:$(PROMETHEUS_PORT)"
	@echo "  Jaeger           http://localhost:$(JAEGER_UI_PORT)"
	@echo "  Loki (API)       http://localhost:$(LOKI_PORT)/ready"
	@echo "  Alloy (debug)    http://localhost:$(ALLOY_UI_PORT)"

.PHONY: down
down: ## Stop the stack (keeps the observability volumes)
	@$(COMPOSE) down --remove-orphans

.PHONY: restore
restore: check-docker ## Restore the initial data: recreate agent and MCP server (in-memory state comes from dados/)
	@$(COMPOSE) up -d --force-recreate --wait --wait-timeout 120 mcp-server agent
	@echo "[ ok ] Agent and MCP server restarted with the initial data from dados/."

.PHONY: restart-mcp
restart-mcp: check-docker ## Restart only the MCP server (proves requestState survives a restart)
	@$(COMPOSE) restart mcp-server
	@$(COMPOSE) up -d --wait --wait-timeout 60 mcp-server
	@echo "[ ok ] MCP server restarted."

.PHONY: logs logs-mcp logs-agent
logs: ## Follow the logs of every service
	@$(COMPOSE) logs -f
logs-mcp: ## Follow the MCP server stderr (method, id, traceparent of each request)
	@$(COMPOSE) logs -f mcp-server
logs-agent: ## Follow the agent logs
	@$(COMPOSE) logs -f agent

.PHONY: ps
ps: ## Show the state of the containers
	@$(COMPOSE) ps

##@ Local run (no Docker, one terminal each)
.PHONY: run-mcp
run-mcp: check-os ## Run the MCP server locally on MCP_PORT (stderr in this terminal)
	@[ -f .env ] || ./scripts/gen_secret.sh
	@source scripts/lib.sh; load_env .env; cd servidor-mcp && PYTHONPATH=src $(UV) run --frozen python -m mcp_server

.PHONY: run-agent
run-agent: check-os ## Run the agent locally on AGENT_PORT (expects the MCP server on MCP_PORT)
	@[ -f .env ] || ./scripts/gen_secret.sh
	@source scripts/lib.sh; load_env .env; cd agente && PYTHONPATH=src $(UV) run --frozen python -m agent

##@ Tests and validation
.PHONY: validate
validate: restore ## Run the official validator against fresh processes (output also in validacao.log)
	@$(VALIDATOR_PYTHON) validador/validar.py --agente $(AGENT_URL) --mcp $(MCP_URL) | tee validacao.log

.PHONY: test-unit
test-unit: ## Unit tests of both services (make up before, make down after)
	$(call with_stack,(cd servidor-mcp && $(UV) run --frozen pytest -q) && (cd agente && $(UV) run --frozen pytest -q) && $(UV) run --frozen pytest -q tests/unit,Unit tests)

.PHONY: test-integration
test-integration: ## Integration tests of the evaluator flows against the running stack
	$(call with_stack,$(MAKE) --no-print-directory restore && AGENT_URL=$(AGENT_URL) MCP_URL=$(MCP_URL) JAEGER_URL=http://localhost:$(JAEGER_UI_PORT) LOKI_URL=http://localhost:$(LOKI_PORT) GRAFANA_URL=http://localhost:$(GRAFANA_PORT) $(UV) run --frozen pytest -q -rA,Integration tests)

.PHONY: tests
tests: check-protected ## Unit + integration tests + official validator (make up before, make down after)
	$(call with_stack,(cd servidor-mcp && $(UV) run --frozen pytest -q) && (cd agente && $(UV) run --frozen pytest -q) && $(UV) run --frozen pytest -q tests/unit && $(MAKE) --no-print-directory restore && AGENT_URL=$(AGENT_URL) MCP_URL=$(MCP_URL) JAEGER_URL=http://localhost:$(JAEGER_UI_PORT) LOKI_URL=http://localhost:$(LOKI_PORT) GRAFANA_URL=http://localhost:$(GRAFANA_PORT) $(UV) run --frozen pytest -q -rA && $(MAKE) --no-print-directory validate,All tests)

##@ Observability
.PHONY: observability
observability: ## Check Prometheus, Grafana, Jaeger, Loki and Alloy (TRACE_ID=<id> prints direct links)
	@for check in "Prometheus|http://localhost:$(PROMETHEUS_PORT)/-/ready" "Grafana|http://localhost:$(GRAFANA_PORT)/api/health" \
		"Jaeger|http://localhost:$(JAEGER_UI_PORT)/" "Loki|http://localhost:$(LOKI_PORT)/ready" "Alloy|http://localhost:$(ALLOY_UI_PORT)/-/ready"; do \
		name=$${check%%|*}; url=$${check##*|}; \
		if curl -fsS -o /dev/null --max-time 3 "$$url"; then echo "[ ok ] $$name $$url"; else echo "[fail] $$name not answering at $$url (make up? make logs)"; fi; \
	done
	@if [ -n "$${TRACE_ID:-}" ]; then \
		echo "  Correlation dashboard: http://localhost:$(GRAFANA_PORT)/d/central-de-salas-correlacao?var-trace_id=$$TRACE_ID"; \
		echo "  Jaeger trace:          http://localhost:$(JAEGER_UI_PORT)/trace/$$TRACE_ID"; fi

.PHONY: traces
traces: ## Print the Jaeger URL (TRACE_ID=<id> prints the trace link, e.g. the one the validator prints)
	@curl -fsS -o /dev/null --max-time 3 http://localhost:$(JAEGER_UI_PORT)/ \
		&& echo "[ ok ] Jaeger UI: http://localhost:$(JAEGER_UI_PORT)" \
		|| { echo "[fail] Jaeger is not answering on port $(JAEGER_UI_PORT). Run make up (or check JAEGER_UI_PORT)."; exit 1; }
	@if [ -n "$${TRACE_ID:-}" ]; then echo "  Trace: http://localhost:$(JAEGER_UI_PORT)/trace/$$TRACE_ID"; fi

.PHONY: dashboards
dashboards: ## Regenerate the Grafana dashboards from scripts/gen_dashboards.py
	@python3 scripts/gen_dashboards.py

##@ Code quality and docs
.PHONY: check-protected
check-protected: ## Fail if dados/, validador/ or exemplos/ differ from the last commit (they must never change)
	@if ! git diff --quiet HEAD -- dados validador exemplos || [ -n "$$(git status --porcelain -- dados validador exemplos)" ]; then \
		echo "[fail] dados/, validador/ or exemplos/ were modified. The evaluator uses the original files:"; \
		git status --short -- dados validador exemplos; \
		echo "  -> restore them: git checkout -- dados validador exemplos"; exit 1; \
	else echo "[ ok ] dados/, validador/ and exemplos/ are untouched."; fi

.PHONY: lint
lint: check-protected ## Ruff (lint + format check) on both services, the TOC check and the protected-files check
	@for dir in servidor-mcp agente .; do (cd $$dir && $(UV) run --frozen ruff check . && $(UV) run --frozen ruff format --check .); done
	@python3 scripts/toc.py --check

.PHONY: fmt
fmt: ## Format code with ruff and refresh the TOCs
	@for dir in servidor-mcp agente .; do (cd $$dir && $(UV) run --frozen ruff format . && $(UV) run --frozen ruff check --fix .); done
	@python3 scripts/toc.py

.PHONY: toc
toc: ## Add or refresh the TOC at the top of every Markdown file (idempotent)
	@python3 scripts/toc.py

.PHONY: clean
clean: ## Remove virtualenvs, caches and build outputs (keeps .env)
	@rm -rf servidor-mcp/.venv agente/.venv .venv dist validacao.log
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	@echo "[ ok ] Clean."
