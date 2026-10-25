# P1-B3: Automatic approved GitHub Issue Harness (staged)

**Status: CODE_IN_REVIEW / LIVE_E2E_NOT_VERIFIED / NO_GO ON CONSUMER AGY.**
Source: [Issue #56](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/56). Stacked on offline P1-B2 integration PR #55; this is **not** a production deployment or autonomous E2E PASS.

## Exact selected workflow

One `harness:approved` GitHub Issue, with an exact
`## Target Directories (allowed paths)` block, triggers a locked-down
GitHub Actions job once the repository has an **independently provisioned
dedicated Enterprise AGY runner**:

```text
GitHub Issue with harness:approved label
  -> Host reads Issue, validates OPEN + scope + SHA
  -> Host creates unique feature worktree from pinned checkout
  -> Gemini Worker (fresh official agy headless task) writes scoped candidate
  -> Host checks paths, fingerprints and secrets
  -> deterministic Python checks plus Gateway/Node ESP-IDF v6.1
     offline Docker builds on a pinned image sha256
  -> Host checks same candidate fingerprint
  -> fresh Gemini Auditor (agy headless, separate snapshot and prompt)
  -> strict Host audit parser and exact reviewed_scope + post-audit SHA check
  -> AWAIT_HUMAN or BLOCKED (max 1 repair; no auto Git/PR merge)
```

The GitHub event pipeline is in
`.github/workflows/harness-issue.yml`, with an explicit environment
`harness-enterprise` and dedicated runner labels `self-hosted,linux,harness-isolated`.
Until the owner provisions and verifies this runner, the job is disabled
by `vars.HARNESS_ENTERPRISE_READY`, which must **not** be set by arbitrary
Issue authors. The runner must NOT contain personal user homes, tokens,
credentials, SSH keys or arbitrary Docker mounts.

## Provider entitlement: IMPORTANT STOP GATE

Official Google documentation:
- [Antigravity FAQ](https://www.antigravity.google/docs/faq/)
  supports **direct AGY CLI scripting/CI**, but *consumer-login AGY
  embedding into third-party coding agents or apps is not supported*.
- [Headless CLI](https://www.antigravity.google/docs/cli/headless/)
  documents `agy -p` with `--model`, `--output-format json`,
  `--json-schema`, `--sandbox`, timeouts and soft-denials.

This repo's automatic Host orchestration **must not use consumer AGY login**.
The owner insists on **Gemini through AGY CLI, not Gemini API**. Hence
full automation requires separately verified provider/Enterprise entitlement
**for the exact embedded Harness use**, and an externally isolated runner.
An operator-supplied policy JSON is a decision record, NOT technical proof.
There is no silently enabled flag that creates isolation or authorization.

Example schema for `/etc/lora-harness/provider-policy.json` on the
isolated runner (do not put it in Git):
```json
{
  "provider": "agy-enterprise-authorized",
  "runner": "externally-isolated",
  "approved": true,
  "evidence_id": "approved-entitlement-and-runtime-review-123"
}
```

Required external evidence before setting
`HARNESS_ENTERPRISE_READY=true`: supported AGY provider entitlement,
runtime/credential separation from all untrusted Worker tools,
direct TCP/DNS/IPv6/host/peer egress controls, process and memory limits,
known pinned `AGY_MODEL`, fixed Docker `HARNESS_IDF_IMAGE_ID`,
v6.1 baseline, account/project cost budget, and an isolated
self-hosted runner with protected environment permissions.
**No tests here prove these external controls.** If no supported Enterprise
entitlement is available, this automatic path remains **BLOCKED**;
continue using the previously proven *operator-direct* dual-AGY workflow.

## CLI status commands

The CLI is preflight-only unless `--execute` is supplied. Example:

```bash
python3 scripts/agent_harness/p1/auto_issue.py --issue 123
```

It checks Issue approval label, state, path scope and source SHA,
but does not invoke Gemini or build. When live environment prerequisites
have been **independently verified**, GitHub Actions is the intended
event-based entrypoint. Do not run `--execute` from a personal WSL2
checkout, copy consumer CLI profiles, give Agent arbitrary GitHub tokens,
enable `--dangerously-skip-permissions`, or manually assume a runner is
secure because a policy JSON says so.

The `--report` output is a sanitized status/result file, not raw model
stdout/stderr. Receipts include issue body SHA, source SHA, candidate
fingerprint, hashed Host command output, model slug and bounded attempt count.
Model transcripts and secrets must not be committed as evidence.
No Git push, auto PR, merge, firmware flashing or RF in this phase.

## Current validation matrix

- Python unit/mock tests + synthetic temporary-Git e2e: software CI only
- Real Gemini Worker/Auditor under the enterprise automatic entrypoint: **NOT_VERIFIED**
- Real ESP-IDF v6.1 Gateway/Node build on the candidate: **NOT_VERIFIED**
- Enterprise/provider permission and credential/network isolation: **NOT_VERIFIED**
- HIL, RF, TDMA timing: **NOT_VERIFIED**
- Autonomous E2E ready: **NO_GO**

Only a real complete run with provider entitlement, isolated execution
and SHA-bound build/audit evidence can change the final readiness status.
