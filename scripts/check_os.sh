#!/usr/bin/env bash
# Supported platforms: Ubuntu 22.04 / 24.04 / 26.04 on amd64, and macOS on amd64 or arm64.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

SUPPORTED_UBUNTU="22.04 24.04 26.04"
os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
  Linux)
    if [ ! -r /etc/os-release ]; then
      fail "Cannot read /etc/os-release to identify the Linux distribution."
      fail "Supported: Ubuntu ${SUPPORTED_UBUNTU// /, } (amd64). See REQUIREMENTS.md."
      exit 1
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    if [ "${ID:-}" != "ubuntu" ] || [[ " $SUPPORTED_UBUNTU " != *" ${VERSION_ID:-} "* ]]; then
      fail "Unsupported Linux: ${PRETTY_NAME:-$ID ${VERSION_ID:-}}."
      fail "Supported: Ubuntu ${SUPPORTED_UBUNTU// /, } (amd64). See REQUIREMENTS.md."
      exit 1
    fi
    if [ "$arch" != "x86_64" ]; then
      fail "Unsupported architecture on Ubuntu: $arch. Supported: x86_64 (amd64). See REQUIREMENTS.md."
      exit 1
    fi
    ok "Supported OS: ${PRETTY_NAME} ($arch) -> follow REQUIREMENTS-UBUNTU.md"
    ;;
  Darwin)
    if [ "$arch" != "x86_64" ] && [ "$arch" != "arm64" ]; then
      fail "Unsupported architecture on macOS: $arch. Supported: x86_64 (Intel) and arm64 (Apple Silicon)."
      exit 1
    fi
    ok "Supported OS: macOS $(sw_vers -productVersion 2>/dev/null || echo '?') ($arch) -> follow REQUIREMENTS-MACOS.md"
    ;;
  *)
    fail "Unsupported operating system: $os ($arch)."
    fail "Supported: Ubuntu ${SUPPORTED_UBUNTU// /, } (amd64) and macOS (amd64/arm64). See REQUIREMENTS.md."
    exit 1
    ;;
esac
