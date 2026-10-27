# P1-B2 C02 / Issue #47 — Dual Gemini via Operator-Direct Antigravity CLI

**Status:** OWNER-SELECTED WORKFLOW DESIGN; operator execution **NOT_VERIFIED**.
[Issue #45](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/45)
records the original Gemini Auditor decision. [Issue #47](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/47)
supersedes the **Worker role for the single supervised pilot**:
**Gemini Worker via `agy`** and **Gemini Auditor via a second `agy`**.
No Gemini API Auditor or Codex Worker in this pilot.
Historical P0/P1 Codex source/adapters are not deleted or rewritten.

## Provider authorization boundary

Official [Antigravity headless docs](https://www.antigravity.google/docs/cli/headless/)
support direct `agy -p` CLI scripting/CI, structured output, model selection
and permission-aware workflows. Official
[FAQ](https://www.antigravity.google/docs/faq/) states that embedding/wrapping
consumer-authenticated `agy` in third-party coding agents or applications
is **not supported** on consumer plans; third-party login reuse/account rotation
is not permitted. Therefore **two directly operator-invoked official CLI sessions**
are the selected workflow. A third-party Harness must **NOT** invoke consumer
`agy` automatically as Worker or Auditor. Full unattended E2E is BLOCKED
pending a supported provider/Enterprise path.

## Trust boundaries — single harmless supervised pilot

| Stage | Selected role | Execution and permission |
|---|---|---|
| Issue and branch | Trusted Host/human | Exact allowlist, baseline SHA; no main edits |
| Worker | **Gemini through direct interactive `agy`** | Human starts CLI in dedicated Issue branch, reviews tool/file-write requests, only creates the README fixture |
| Validation | Host | Check `git status`, changed-path allowlist, secrets/symlinks, deterministic tests and exact candidate hash; compile/build only with correct v6.1 toolchain |
| Independent review | **Gemini through fresh direct `agy -p`** | New context on copied read-only snapshot; no `--continue`, no write/terminal tools; JSON report constrained by committed audit schema |
| Receipt gate | Host | Reject nonzero exit, soft denials, malformed JSON, scope extras/duplicates/missing, SHA drift; FAIL and INCONCLUSIVE never become PASS |
| Decision | Human | `AWAIT_HUMAN`, no auto-push, PR publication, merge, flash or RF |

The two roles are **context-separated, NOT model/provider-independent**. Do not
describe them as a model-independent security audit.

## Operator check, isolation status and resource controls

Use the [operator runbook](../../docs/development/agy-supervised-pilot.md).
For AGY Worker use **interactive operator review**, no
`--dangerously-skip-permissions`, no Turbo/unrestricted mode, and
no automatic tool escalation. AGY Auditor should receive a physically
separate, bounded, copied read-only snapshot with a new conversation.
Permissions, prompt instructions and `--sandbox` alone are not a verified
filesystem boundary: an independently enforced read-only mount remains
NOT_VERIFIED until evidenced. Do not give the Auditor write access.

The owner **deferred the credential-free isolation test**, so H01/H02 and
host/peer/DNS egress resistance remain NOT_VERIFIED. Deferring tests does not
make unattended coding safe. No credentials, profiles, tokens, secret provider
configuration, proxy, Docker or network settings may be altered by this Issue.
Use only locally authorized direct CLI account sessions, never copied login data.

## Gate/evidence limitations

- Repo code/scopes, source SHA, candidate diff and `reviewed_scope` must be
  independently inspected; the Host's Issue #43 validator enforces report shape.
- CI PASS is **not** an AGY Worker run, a real Gemini Auditor assessment, a
  v6.1 firmware build, hardware RF/timing measurement or a security sign-off.
- Mandatory single-pilot acceptance: one harmless README change, one real
  direct Worker session, deterministic Host checks, one fresh operator-direct
  Auditor review, exact candidate binding and final human disposition.
- This workflow is **SUPERVISED_ONLY**. M01/M02 review and H01/H02/H04 closure
  remain separate. No autonomous E2E or deployment approval is implied.
