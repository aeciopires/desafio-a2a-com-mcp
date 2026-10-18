#!/usr/bin/env bash
# Checks every tool the project needs and prints the official install URL for what is missing.
# Docker and Docker Compose come from the OS (Colima on macOS); Python and uv come from mise.
set -uo pipefail
source "$(dirname "$0")/lib.sh"

missing=0
os="$(uname -s)"
MISE_BIN="${MISE_BIN:-$(command -v mise || echo "$HOME/.local/bin/mise")}"

need() {  # need <label> <check-command> <how-to-fix>
  local label="$1" check="$2" fix="$3"
  if out="$(eval "$check" 2>/dev/null)" && [ -n "$out" ]; then
    ok "$label: $(echo "$out" | head -1)"
  else
    missing=1
    fail "$label: not found or not working"
    fail "  -> $fix"
  fi
}

need "make" "make --version" "Ubuntu: sudo apt-get install -y make | macOS: xcode-select --install"
need "curl" "curl --version" "Ubuntu: sudo apt-get install -y curl | macOS: preinstalled"
need "git" "git --version" "https://git-scm.com/downloads"

if [ -x "$MISE_BIN" ]; then
  ok "mise: $("$MISE_BIN" --version 2>/dev/null | head -1)"
  need "python (mise)" "$MISE_BIN exec -- python --version" "run: make install (installs the Python pinned in mise.toml)"
  need "uv (mise)" "$MISE_BIN exec -- uv --version" "run: make install (installs the uv pinned in mise.toml)"
else
  missing=1
  fail "mise: not found"
  fail "  -> run: make install   (official guide: https://mise.jdx.dev/getting-started.html)"
fi
need "python3 (system, for the validator)" "python3 --version" "Ubuntu: sudo apt-get install -y python3 | macOS: xcode-select --install"

if [ "$os" = "Darwin" ]; then
  docker_url="https://github.com/abiosoft/colima#installation (brew install colima docker docker-compose docker-buildx)"
  need "colima" "colima version" "$docker_url"
  if command -v colima >/dev/null 2>&1 && ! colima status >/dev/null 2>&1; then
    missing=1
    fail "colima is installed but its VM is not running -> run: colima start --cpu 2 --memory 4"
  fi
else
  docker_url="https://docs.docker.com/engine/install/ubuntu/"
fi
need "docker" "docker --version" "$docker_url"
need "docker compose v2" "docker compose version" \
  "Ubuntu: https://docs.docker.com/compose/install/linux/ | macOS: brew install docker-compose (see REQUIREMENTS-MACOS.md)"
need "docker buildx" "docker buildx version" \
  "Ubuntu: sudo apt-get install -y docker-buildx-plugin | macOS: brew install docker-buildx"
need "docker daemon" "docker info --format '{{.ServerVersion}}'" \
  "start it (Ubuntu: sudo systemctl start docker; macOS: colima start). Permission denied? https://docs.docker.com/engine/install/linux-postinstall/"

"$(dirname "$0")/check_ports.sh" --skip-own || missing=1

if [ "$missing" -ne 0 ]; then
  fail "Some requirements are missing. Fix the items above (details in REQUIREMENTS.md) and run 'make check-dependencies' again."
  exit 1
fi
ok "All requirements satisfied."
