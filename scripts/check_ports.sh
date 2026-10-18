#!/usr/bin/env bash
# Fails when a host port the stack publishes is already taken, and says how to change it.
# Usage: check_ports.sh [--skip-own]   (--skip-own ignores ports held by this compose project)
# Portable to the bash 3.2 shipped with macOS (no associative arrays).
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env .env

SPECS="AGENT_PORT:7300 MCP_PORT:7301 PROMETHEUS_PORT:9090 GRAFANA_PORT:3000 JAEGER_UI_PORT:16686 JAEGER_OTLP_HTTP_PORT:4318 LOKI_PORT:3100 ALLOY_UI_PORT:12345"

own_ports=""
if [ "${1:-}" = "--skip-own" ] && command -v docker >/dev/null 2>&1; then
  own_ports="$(docker compose ps --format '{{.Ports}}' 2>/dev/null | grep -oE ':[0-9]+->' | tr -d ':>-' | sort -u | tr '\n' ' ' || true)"
fi

holder() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnpH "sport = :$port" 2>/dev/null | head -1
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sed -n '2p'
  fi
}

busy=0
summary=""
for spec in $SPECS; do
  var="${spec%%:*}"
  default="${spec##*:}"
  port="${!var:-$default}"
  summary="$summary $var=$port"
  case " $own_ports " in *" $port "*) continue ;; esac
  line="$(holder "$port")"
  if [ -n "$line" ]; then
    busy=1
    fail "Port $port ($var) is already in use: $line"
    fail "  -> pick another one, e.g.: echo '$var=$((port + 10))' >> .env   (or: export $var=$((port + 10)))"
  fi
done

[ "$busy" -eq 0 ] || exit 1
ok "All published ports are free:$summary"
