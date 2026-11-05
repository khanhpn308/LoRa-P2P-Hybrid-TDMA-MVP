#!/usr/bin/env bash
# Read-only by default without a TTY; interactive MCP install requires explicit approval.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
PROFILE="core"
JSON=0
ONLINE=0
INSTALL_CORE=0
INSTALL_MCP=0
CONFIGURE_NATIVE=0

usage() {
  cat <<'HELP'
Usage: bash scripts/setup_harness.sh [--profile core|firmware|infra|all]
       [--json] [--check-auth] [--install-core] [--install-mcp] [--configure-native] [--help]

Default: offline diagnostics, with optional interactive MCP onboarding prompt on first setup.
Non-interactive or --json: read-only; no sudo, downloads or file edits.
--configure-native: inspect, plan, confirm, and bootstrap Codex/AGY native execution capability.
--install-core: explicitly opt in to apt packages python3/git/gh (prompted).
--install-mcp: inspect, confirm, install pinned SDK, smoke and register Codex/AGY.
--check-auth: opt in to gh auth status (may contact GitHub).
Firmware profile checks local Docker engine + cached ESP-IDF v6.1 image.
Infra profile checks Docker engine and Docker Compose.
HELP
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      [ "$#" -ge 2 ] || { echo "Missing --profile value" >&2; exit 2; }
      PROFILE="$2"; shift 2 ;;
    --json) JSON=1; shift ;;
    --check-auth) ONLINE=1; shift ;;
    --install-core) INSTALL_CORE=1; shift ;;
    --install-mcp) INSTALL_MCP=1; shift ;;
    --configure-native) CONFIGURE_NATIVE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$PROFILE" in core|firmware|infra|all) ;; *)
  echo "Invalid profile: $PROFILE" >&2; exit 2 ;; esac

if [ "$INSTALL_MCP" -eq 1 ] && [ "$JSON" -eq 1 ]; then
  echo "--json and --install-mcp cannot be combined" >&2; exit 2
fi

if [ "$INSTALL_CORE" -eq 1 ]; then
  [ "$JSON" -eq 0 ] || { echo "--json and --install-core cannot be combined" >&2; exit 2; }
  [ -f /etc/os-release ] || { echo "Automatic package mode requires Debian/Ubuntu." >&2; exit 2; }
  # Do not execute untrusted shell content; /etc/os-release is the local OS file.
  . /etc/os-release
  case "$ID" in ubuntu|debian) ;; *)
    echo "Package install is only supported for Ubuntu/Debian; install manually." >&2
    exit 2 ;; esac
  command -v apt-get >/dev/null || { echo "apt-get unavailable" >&2; exit 2; }
  set --
  command -v python3 >/dev/null || set -- "$@" python3
  command -v git >/dev/null || set -- "$@" git
  command -v gh >/dev/null || set -- "$@" gh
  if [ "$#" -gt 0 ]; then
    printf 'Proposed packages (no Docker or AI CLI):\n'
    printf '  %s\n' "$@"
    printf 'Requires sudo apt-get update/install and network access.\n'
    printf 'Type INSTALL to approve these exact packages: '
    read -r CONFIRM || { echo "Cancelled" >&2; exit 1; }
    [ "$CONFIRM" = INSTALL ] || { echo "Cancelled; no packages changed." >&2; exit 1; }
    command -v sudo >/dev/null || { echo "sudo unavailable" >&2; exit 1; }
    sudo apt-get update
    sudo apt-get install -y -- "$@"
  else
    echo "Core executables already present; no package changes."
  fi
fi

if ! command -v python3 >/dev/null; then
  echo "Python3 missing. On Ubuntu, run: sudo apt-get install python3" >&2
  echo "Or use --install-core for an explicit interactive package plan." >&2
  exit 1
fi

if [ "$CONFIGURE_NATIVE" -eq 1 ]; then
  if [ "$JSON" -eq 1 ]; then
    exec python3 "$ROOT/scripts/harness_native_setup.py" --plan --json
  else
    exec python3 "$ROOT/scripts/harness_native_setup.py" --apply
  fi
fi

# Only an interactive first run can write user MCP config after approval.
if [ "$INSTALL_MCP" -eq 1 ]; then
  python3 "$ROOT/scripts/harness_mcp_setup.py" --apply || exit 1
elif [ "$JSON" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then
  if python3 "$ROOT/scripts/harness_mcp_setup.py" --needs-setup; then
    if ! python3 "$ROOT/scripts/harness_mcp_setup.py" --apply; then
      echo "MCP setup cancelled/blocked; core diagnostics will continue." >&2
    fi
  fi
fi

set -- --profile "$PROFILE"
if [ "$JSON" -eq 1 ]; then set -- "$@" --json; fi
if [ "$ONLINE" -eq 1 ]; then set -- "$@" --check-auth; fi
exec python3 "$ROOT/scripts/harness_doctor.py" "$@"
