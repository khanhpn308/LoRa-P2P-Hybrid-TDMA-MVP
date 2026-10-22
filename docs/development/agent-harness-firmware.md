# Firmware AI Coding Harness — P0 Codex + Antigravity

**Status: DRAFT, Issue #30, PR #31.** This is a controlled software pilot, NOT an unattended production runner and NOT a firmware implementation.

## Architecture and scope

- LoRa **P2P**, ESP32 + SX1276, local Gateway TDMA Master; Go Backend plans schedules. No LoRaWAN assumptions.
- Existing firmware is only a scaffold; experimental driver has not been imported.
- Radio-MAC v1 wire/security remains DRAFT; no production codec, RF limits or radio performance may be approved by Agent output.
- **Owner-approved ESP-IDF baseline `v6.1`:** ADR-0003 and `firmware/esp-idf-version.txt` are the source of truth. Gateway/Node CI and Harness share the same version; driver porting/HIL still require separate verification.
- Keep original acceptance gates G0–G6 in `docs/verification/acceptance-gates.md` separate from host software checks.

## P0 implemented in this PR

1. Python Host preflight reads an OPEN GitHub Issue with an explicit, exact `Target Directories (allowed paths)` list, refuses a dirty worktree and requires an Issue-number feature branch.
2. Codex CLI acts as the Worker in `workspace-write` mode. The Host, not Worker text, validates all changes; file scope, symlink changes and binary or oversized diffs are rejected.
3. Deterministic Host checks run structure tests, Python harness unit tests and BOTH ESP-IDF app builds. A Docker-first Toolchain Resolver selects the **owner-approved v6.1 release**, verifies the local official Espressif image identity and checks `idf.py --version`. Host records image ID/version plus command receipts; it does not put raw logs in the manifest.
4. Antigravity CLI (`agy`) acts as fresh independent Auditor. Host creates a bounded copied snapshot of changed code and relevant reference docs, embeds full review data into the prompt, and uses `--output-format json`, `--json-schema` and `--sandbox`.
5. `exit_code == 0` alone is NOT success. Host requires `status=SUCCESS`, nonmissing `structured_output`, a structurally valid report, zero findings/limitations for PASS, explicit per-changed-file `reviewed_scope`, and no observed permission soft-denial.
6. Host verifies audit snapshot integrity after the model invocation. Up to two OPTIONAL repair rounds are supported; repeated identical diff, timeout, scope violation and audit INCONCLUSIVE stop the job.
7. Each P0 run creates a unique ignored `artifacts/agent-harness/<run-id>/manifest.json`. `BUILD_VERIFIED_LOCAL_UNCOMMITTED_TREE` and `AUDIT_PASS_SOFTWARE_ONLY` never imply real HIL or RF verification.

## Quick checks, no model/token usage

On a clean clone with `chore/30-firmware-agent-harness` checked out:

```bash
python3 -m compileall -q scripts/agent_harness tests/agent_harness
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/agent_harness/run.py --issue 30
```

Last command is PREFLIGHT ONLY. It requires `gh` login and a clean Issue-number branch. It does not call Codex, AGY or ESP-IDF.

## Explicit local pilot only on a disposable isolated runner

**Do not run `--execute` on a credentialed personal WSL2 machine.** Prepare a disposable VM/container and per-Issue worktree, with controlled network, separate authorized provider credentials, no personal home/SSH tokens, no privileged Docker socket, limited CPU/time, and external host-owned evidence/approval.

After Issue scope and board pinout are approved, run from the isolated Issue branch; the repo baseline is `v6.1` and the version flag is an optional cross-check:

```bash
python3 scripts/agent_harness/run.py --issue 10 --execute \
  --accept-isolated-pilot \
  --expected-idf-version 'v6.1' \
  --max-repairs 1
```

The flag `--accept-isolated-pilot` is ONLY an acknowledgment, not isolation or enforcement. The runner cannot attest Docker/VM isolation. Codex and AGY internal sandbox flags also do not replace a strong external boundary. The host does not commit, push, merge, open PRs, flash ESP32, transmit RF or approve HIL in P0.

## Portable ESP-IDF Toolchain Resolver (implemented in P0)

File: `scripts/agent_harness/toolchains/resolver.py`. This resolver is controlled by the Python Host; neither Codex nor AGY may choose the ESP-IDF version. This implements the owner-approved v6.1 baseline; firmware build/HIL validation remains separate.

### Docker-first (default, no machine-specific IDF_PATH)

1. ADR-0003 and `firmware/esp-idf-version.txt` approve **`v6.1`**. Do not use `latest`, prereleases or floating `release-v6.1` tags.
2. A trusted operator pre-installs the corresponding official `espressif/idf:v6.1` image. The Harness never pulls images or selects a new firmware version autonomously.
3. Host runs `docker image inspect` and requires a valid SHA-256 image identity; executes **that inspected image ID** with `--pull=never`. A `docker run ... idf.py --version` probe must match the approved exact release.
4. Builds bind only the current repository/worktree to `/workspace` and use `--network=none`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--read-only`, a writable `/tmp` tmpfs, bounded processes/memory/CPU and non-root UID/GID. No USB device, Docker socket or privileged flag is exposed.
5. Container project workdirs are derived from the worktree at runtime. No `/home/<user>/...` path is embedded in source, and no `source export.sh` is needed.

Example **operator preparation only**, after the version has been formally approved:

```bash
docker version
docker pull espressif/idf:v6.1  # Operator prepares the approved image
docker image inspect espressif/idf:v6.1 --format '{{.Id}}'
```

Verify the selected environment WITHOUT starting Codex/AGY, firmware builds or RF:

```bash
python3 scripts/agent_harness/toolchains/check.py --version 6.1
# Only if approved to use the native installation:
python3 scripts/agent_harness/toolchains/check.py --version 6.1 --mode native_only
```

The standalone command returns `TOOLCHAIN_VERIFIED_ONLY` or `BLOCKED`. These commands check the repository-approved ESP-IDF v6.1. A successful probe is NOT an ESP-IDF build, RF or HIL PASS.

Start the controlled CLI pilot only in an **externally isolated disposable** execution environment:

```bash
python3 scripts/agent_harness/run.py --issue 10 --execute \
  --accept-isolated-pilot \
  --expected-idf-version '6.1' \
  --toolchain-mode container_first
```

The version is pinned to `v6.1`; the Issue number must match the feature branch. Image availability and version are checked **before the Worker runs**. A failed probe yields `BLOCKED`, never `BUILD_VERIFIED`. Version is loaded from `firmware/esp-idf-version.txt` by default; `--expected-idf-version` or `check.py --version` may only assert the same value.

### Native discovery (explicitly opted into host execution)

- `--toolchain-mode native_only`: use an already activated `idf.py` on PATH, or source a trusted `export.sh` from environment-provided `IDF_PATH` / `ESP_IDF_ROOT` in the SAME child Bash process that runs `idf.py`.
- `--toolchain-mode native_first`: native first, Docker if it cannot match the version.
- `--toolchain-mode container_first --allow-native-fallback`: Docker first, then native with explicit fallback permission.
- `--toolchain-mode container_only`: Docker only; never use native tools.
- The native resolver does not recursively scan personal directories, trust unvetted startup files, download installers or silently fall back. When installed somewhere nonstandard, let the environment supply `IDF_PATH` or use the container.

Example without hardcoding a path into repository source:

```bash
# IDF_PATH comes from the machine's ESP-IDF installation/VS Code setup.
# No source-code path or recursive HOME scan is needed.
test -n "$IDF_PATH" && test -f "$IDF_PATH/export.sh"
python3 scripts/agent_harness/run.py --issue 10 --execute \
  --accept-isolated-pilot \
  --expected-idf-version 'v6.1' \
  --toolchain-mode native_only
```

**Security boundary:** Native builds run untrusted Worker-modified CMake/scripts on the host; permit this ONLY inside a disposable credential-isolated VM/container. Docker build restrictions protect the build subprocess, **not** the Codex Worker. Docker-daemon access itself is privileged; only the trusted Host may invoke Docker, and a stronger isolated runner remains required for unattended P1.

**Operational limitations:** Builds with no network may fail if managed components need downloading; prepare and review dependencies before running. Image availability, Docker daemon permissions, correct patch tag and WSL2 behavior are still `NOT_VERIFIED` until exercised on the target host. Flash, monitor, HIL, RF and real TDMA remain outside this runner.

### Verification

`python3 -m unittest discover -s tests/agent_harness -v` tests successful and failed version resolution, missing Docker, exact release checks, source activation with spaces, and restricted Docker command construction by mock; no container image download, model calls or RF use in CI.
## What remains to implement (P1 and later)

- Real provisioned **isolated per-Issue Git Worktree**, filesystem/network/identity boundaries and least-privilege short-lived GitHub publisher. Containerized ESP-IDF builds alone do not provide this full runner isolation.
- Durable SQLite checkpoints, recovery after process/WSL crash, process-tree cleanup, resource budgets and verified tool versions.
- Full immutable logs with secret redaction, static analysis, code-coverage policy, CI evidence bound to a final commit SHA, security scanning and automatic Draft PR.
- Model-agnostic routing for `agy` Worker / Codex Auditor; quota/rate-limit tracking under provider authorization.
- Lab-controlled HIL/logic-analyzer/RF testing with real board metadata and human technical sign-off.

**P0 evidence scope:** Pure-Python tests and GitHub Actions validate the harness software. Live Codex/AGY credentials, unattended sandbox security, firmware build, RF/TDMA and HIL are **NOT_VERIFIED** until separately measured.

## Official CLI guidance

- https://antigravity.google/docs/cli/headless/
- https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex
- https://developers.openai.com/blog/codex-as-a-platform
