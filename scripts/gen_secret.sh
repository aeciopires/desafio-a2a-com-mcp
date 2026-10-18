#!/usr/bin/env bash
# Creates .env from .env.example if needed and fills the secrets that are still empty.
# Existing values are never overwritten (the requestState key must survive restarts).
set -euo pipefail
source "$(dirname "$0")/lib.sh"

[ -f .env ] || { cp .env.example .env; info "Created .env from .env.example"; }

random_hex() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_hex($1))"
  else
    openssl rand -hex "$1"
  fi
}

fill() {
  local key="$1" bytes="$2" current
  current="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- || true)"
  if [ -n "$current" ]; then
    ok "$key already set in .env (kept)"
    return
  fi
  local value
  value="$(random_hex "$bytes")"
  if grep -qE "^${key}=" .env; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
  ok "$key generated and written to .env"
}

fill REQUEST_STATE_SECRET 32
fill GRAFANA_ADMIN_PASSWORD 12
chmod 600 .env
