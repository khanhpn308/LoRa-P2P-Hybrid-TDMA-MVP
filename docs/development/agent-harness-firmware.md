# Autonomous Firmware Agent Harness — ESP32 + SX1276 (pilot)

**Status:** DRAFT / pilot infrastructure only, Issue #30. No unattended production capability or firmware changes claimed.

## 1. What actually exists

The current monorepo firmware apps are scaffolds; shared SX1276/MAC/TDMA components are not yet ported. `.github/workflows/ci-firmware.yml` presently builds with ESP-IDF release-v5.4, whereas `esp32e_sx1768-915Mhz` experimental code was developed for v6.1. **BLOCKER:** Decide and document the approved toolchain version before importing the old driver. Issue #9 confirms PCB, #10 provisions driver. Do not assert legal transmit parameters without regional compliance assessment.

This harness is deliberately NOT a copy of a social-media three-level template. It supplements existing `.github/`, `contracts/`, requirements, ADR and verification gates as single sources of truth.

## 2. Roles & trust boundaries

| Role | Initial tool | Permissions | Output |
|---|---|---|---|
| Host | Python, git, gh, idf.py | Owned deterministic operations | exit codes, SHA-linked evidence |
| Worker | Codex CLI (`codex exec`) | **workspace-write sandbox**, no approval for escalation | source/tests/diff (never certification) |
| Auditor | Gemini CLI new headless process | non-editing, plan/read-only | JSON review with file:line findings |
| Humans | Embedded/RF owners & GitHub CODEOWNERS | Approve hardware, RF, ISR/timer/security and contract changes | explicit review/merge |

Running two assistants with the same specifications reduces self-review bias but **does not prove independence from shared specification errors**. For critical radio or timing work, involve a human and hardware test. Agent text cannot upgrade verification status.

## 3. Pilot runbook (WSL2 / developer-owned machine)

Prerequisites: `python3`, `git`, GitHub CLI `gh` authenticated with appropriate scopes, Codex CLI authenticated through supported login, Gemini CLI separately authenticated with an authorized Google account, and selected ESP-IDF toolchain. Do not commit `~/.codex`, `~/.gemini`, API keys or session tokens. Confirm actual CLI flags with `codex --help` and `gemini --help` before unattended execution.

```bash
git clone git@github.com:khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP.git
cd LoRa-P2P-Hybrid-TDMA-MVP
git switch main && git pull --ff-only
git switch -c feature/10-sx1276-driver
# Scope, acceptance criteria, version, board assumptions must be reviewed first.
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/agent_harness/run.py --issue 10
# Only on a sandboxed, credential-isolated development runner with verified CLI:
python3 scripts/agent_harness/run.py --issue 10 --execute
```

Default invocation is **preflight only**; it never invokes an AI or changes files. `--execute` starts a bounded Worker invocation, checks all changes against Issue paths, runs structure and two ESP-IDF builds using the INSTALLED toolchain, and submits the diff and logs to a fresh Gemini Auditor. Stops on all failures or absent tools. Evidence is written under ignored `artifacts/agent-harness/`. It does **not** commit/push/create PR, flash hardware or perform RF. It does **not** retry forever or background itself; use supervised pilot runs before enabling a scheduled external runner.

After successful evidence collection, a trusted host operator creates a **draft PR** linked to the Issue and attaches the manifest/logs. Human review and HIL/RF remain separate. Host CI tests harness's pure-Python gates on PRs; it does not run billable model calls on GitHub-hosted Actions.

### Important security boundary

`--execute` is a **developer pilot**, not a hardened sandbox. A model may author build scripts inside its approved paths; subsequently executing an unreviewed build on a credentialed host is unsafe. For unattended mode, run the entire Worker's code/build in a disposable container/VM with no personal home mount, no SSH or cloud keys, no privileged Docker socket, restricted network/CPU/time, and upload **only** evidence plus a draft PR using a narrow-scope host process. Keep HIL on an explicit operator-controlled lab runner. Do not use `--yolo` on an unrestricted host.

Multiple Gemini Pro accounts are not a rate-limit bypass or interchangeable pooled tokens. Use only accounts legitimately authorized for their own sessions; no automated credential rotation to evade quotas. Gemini CLI's OAuth credential must not be extracted/piggybacked by another service. For provider-neutral, long-running automation use licensed APIs under their billing/terms, not assume that Gemini Pro or ChatGPT Plus includes unlimited API capacity.

## 4. Host acceptance logic

```text
Issue/approved scoped paths + clean feature branch
    -> Worker creates code (CODE_WRITTEN)
    -> Scope/path & symlink guard
    -> tools: structure, unit, static checks, gateway & node build
    -> Auditor: independent semantic review
    -> local evidence artifact and human-reviewed draft PR
    -> human HIL/RF/Timing evidence if issue calls for it
    -> human merge
```

The host must distinguish `BUILD_VERIFIED`, `AUDIT_PASS`, `HIL_VERIFIED`, `RF_VERIFIED`. Missing toolchain/build = `NOT_VERIFIED`, not success. Logs for a mutable worktree are **pre-commit**; re-run required gates on the resulting commit SHA before merge. CI pass alone is not proof of radio timing.

## 5. Roadmap / rollout limits

- **P0 (this PR):** policy, explicit Worker/Auditor contracts, Issue scope guard, pilot CLI coordinator, pure-Python tests and CI. No actual provider run or `idf.py` here; `NOT_VERIFIED`.
- **P1:** dockerized isolated runner, per-Issue worktree, short-lived job identity, artifact log SHA/metadata, diff/secrets check, retry cap + failure triage, draft PR publisher with limited GitHub token and code review approvals.
- **P2:** HIL lab agent separated from development sandbox; real board revision/instrument and deterministic timestamps; timing tests and reproducible RF compliance records. Never autonomous firmware flashing/transmitting from the cloud.
- **P3:** policy-backed Issue queue, parallel independent worktrees (not same file), monitoring/alerts/cost budget and stop-on-risk. No auto-merge for critical firmware.

Track efficiency after pilot: first-pass reviewer success, real defects caught, false positives, iteration count, wall time, token consumption, and escaped defects.

## 6. Why the project cannot yet be called autonomous

The GitHub repository contains scaffolds and has no evidence that Gemini/Codex CLI credentials, a dedicated isolated runner, approved ESP-IDF target version, a hardware lab or release gate automation are installed. This change configures a **reproducible starting point**, not a deployed always-on agent service. The owner decides when to enable P1 after validating security and audit output.
