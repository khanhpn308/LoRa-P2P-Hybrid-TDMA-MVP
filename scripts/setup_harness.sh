#!/usr/bin/env bash
# Read-only offline diagnostics by default; installation requires explicit opt-in flags.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
REPO="$ROOT"
PROFILE="core"
JSON=0
ONLINE=0
SMOKE=0
INSTALL_CORE=0
INSTALL_MCP=0

usage() {
  cat <<'HELP'
Usage: bash scripts/setup_harness.sh [--profile core|firmware|backend|web|infra|all]
       [--repo PATH] [--json] [--smoke] [--check-auth] [--install-core] [--install-mcp] [--help]

Default: offline read-only diagnostics; no sudo, downloads, package installs, or file edits.
--repo PATH: inspect a specific repository checkout or worktree (default: script repo root).
--smoke: run read-only baseline smoke checks (G0, structure, quality gates, firmware toolchain).
--install-core: explicitly opt in to apt packages python3/git/gh (interactive confirmation).
--install-mcp: explicitly opt in to install pinned optional MCP SDK v2.3.0 and register Codex/AGY.
--check-auth: opt in to gh auth status (may contact GitHub).
Firmware profile checks local Docker engine + ESP-IDF v6.1 image + managed_components cache.
Backend profile checks .go-version / go.mod pin + host/Docker Go 1.27.3 toolchain.
Web profile checks package-lock.json + node/npm + node_modules dependency cache.
Infra profile checks Docker engine and Docker Compose.
HELP
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      [ "$#" -ge 2 ] || { echo "Missing --profile value" >&2; exit 2; }
      PROFILE="$2"; shift 2 ;;
    --repo)
      [ "$#" -ge 2 ] || { echo "Missing --repo value" >&2; exit 2; }
      REPO="$2"; shift 2 ;;
    --json) JSON=1; shift ;;
    --smoke) SMOKE=1; shift ;;
    --check-auth) ONLINE=1; shift ;;
    --install-core) INSTALL_CORE=1; shift ;;
    --install-mcp) INSTALL_MCP=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$PROFILE" in core|firmware|backend|web|infra|all) ;; *)
  echo "Invalid profile: $PROFILE" >&2; exit 2 ;; esac

if [ "$INSTALL_MCP" -eq 1 ] && { [ "$JSON" -eq 1 ] || [ "$SMOKE" -eq 1 ]; }; then
  echo "--install-mcp cannot be combined with --json or --smoke" >&2; exit 2
fi

if [ "$INSTALL_CORE" -eq 1 ]; then
  [ "$JSON" -eq 0 ] && [ "$SMOKE" -eq 0 ] || { echo "--install-core cannot be combined with --json or --smoke" >&2; exit 2; }
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

# Optional MCP onboarding only runs when explicitly requested via --install-mcp.
if [ "$INSTALL_MCP" -eq 1 ]; then
  python3 "$ROOT/scripts/harness_mcp_setup.py" --apply || exit 1
fi

set -- --profile "$PROFILE" --repo "$REPO"
if [ "$JSON" -eq 1 ]; then set -- "$@" --json; fi
if [ "$ONLINE" -eq 1 ]; then set -- "$@" --check-auth; fi
if [ "$SMOKE" -eq 1 ]; then set -- "$@" --smoke; fi
exec python3 "$ROOT/scripts/harness_doctor.py" "$@"
