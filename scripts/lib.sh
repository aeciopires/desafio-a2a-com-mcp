#!/usr/bin/env bash
# Shared helpers for the scripts called by the Makefile.

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
fi

info()  { printf '%s[info]%s %s\n' "$BLUE" "$RESET" "$*"; }
ok()    { printf '%s[ ok ]%s %s\n' "$GREEN" "$RESET" "$*"; }
warn()  { printf '%s[warn]%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
fail()  { printf '%s[fail]%s %s\n' "$RED" "$RESET" "$*" >&2; }

# Load .env without overriding variables already exported in the shell.
load_env() {
  local file="${1:-.env}"
  [ -f "$file" ] || return 0
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
    key="${key//[[:space:]]/}"
    if [ -z "${!key:-}" ] && [ -n "$value" ]; then
      export "$key=$value"
    fi
  done < "$file"
  return 0
}
