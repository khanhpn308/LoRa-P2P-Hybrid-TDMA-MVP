# P1-B2 C02 — Provider Identity and Credential Isolation Decision

**Status: DRAFT / PROPOSED. NOT APPROVED FOR LIVE MODEL EXECUTION.**
Owner decision required. Tracked by [Issue #45](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/45).
Baseline for this design draft: `237ae6b5ebda504035f2beabfb4495cfd27e2f09`; [Issue #34](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/34) remains OPEN and [PR #38](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/38) remains Draft.

## 1. Scope and evidence

This document chooses the **smallest candidate architecture** for a single supervised E2E pilot. It does not authorize key provisioning, quota/billing expenditure, provider inference calls, Docker changes, firewall policy, code execution, firmware changes or E2E certification.

Vendor reference snapshot (2026-10-23):
- Google [Antigravity FAQ](https://www.antigravity.google/docs/faq/): consumer headless `agy -p` may be used directly for scripting/CI; embedding it in a third-party coding agent/app or rotating accounts is **not supported**. The historical AGY Docker smoke receipt `READ_ONLY_MODEL_PROBE_PASS_ONLY` is **not** authorization for consumer-login orchestration.
- OpenAI [Codex non-interactive guidance](https://learn.chatgpt.com/docs/non-interactive-mode): `codex exec` supports CI/scripting. Official guidance warns against exposing API keys to untrusted code and recommends supported project/API authentication for automation.
- Google [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key): use an authentication-enabled key and server-side secret management; project eligibility, quotas and pricing must be verified live. Do not assume a new service account is allowed.

## 2. Proposed minimal provider choice (pending owner approval)

| Role | Proposed supported transport | Trust boundary |
|---|---|---|
| Worker inference | OpenAI API-backed Codex or supported `codex exec` with a verified external credential broker | No arbitrary shell/tool/plugin access from an authenticated inference process; if CLI cannot ensure separation, use Host-mediated official API or BLOCK |
| Independent Auditor inference | Gemini API with separately authorized authentication-enabled key | Read-only immutable snapshot, no shell/tools, separate request/context/identity, structured report |
| Host coordinator | Deterministic trusted process only | Owns Issue scope, Git, target SHA, bounded tool dispatch, build and code audit validation, evidence and final decision |
| Worker code executor | Disposable credential-free external VM/runner | Pre-approved files only, no host home, Docker socket, GitHub write token or direct internet; strict budgets |
| Build/test | Trusted offline ESP-IDF v6.1 stage | Network disabled, candidate SHA verified, no model credentials |

The two model providers are *proposed* for compatibility, not proof of user-account entitlement. One supervised pilot, one Worker, one independent Auditor, at most one bounded repair. No publishing, merge, flash or RF transmission during the pilot.

## 3. Trust boundaries

```text
        [Human / approved GitHub Issue]
                    |
              Trusted Host
        (scope, SHA, approvals, logs)
           /       |        \
          v        v         v
  [Inference]  [Executor] [Auditor inference]
  Broker A      VM/no key   Broker B / Gemini API
  Codex/API     no internet no tools / read-only
  key owned    only Host RPC separate credential
  externally        |
                  candidate
                    |
                Offline Build
                    |
               Host validator
                    |
               AWAIT_HUMAN
```

The authenticated inference client **must not execute untrusted commands or mount arbitrary Worker writable files**. The Worker executor **must not receive API tokens or persistent login profiles**; a subprocess `env` or RW credential mount is not a security boundary. An untrusted Worker cannot choose arbitrary upstream destinations. The Host validates actual changed paths and fingerprints before/after tools, build, audit and repair.

### Mandatory network enforcement

A Docker `--internal` bridge and `HTTP_PROXY` variables are insufficient on their own. WP-2 must demonstrate outbound constraints for direct TCP, UDP/DNS, host gateway, peer containers, IPv6, DNS rebinding, proxy-down fallback, and numeric/IP/CNAME authority, with **credential-free probes** in the actual namespace and positive controls. No network attestation is inferred from historical smoke.

## 4. Identity, secret and quota lifecycle (owner decisions required)

1. Confirm a **supported** project-level OpenAI coding route and Google Gemini API route; validate account ownership and third-party use rights for this exact Harness workflow.
2. Approve costs and a per-job hard token/monetary quota before any API call. ChatGPT/consumer subscriptions do not imply API credit.
3. Provision a distinct credential per provider only into a trusted secret storage/broker. Never put tokens in Issue/PR text, repository, Docker layers, arbitrary Worker process env, tool output or evidence.
4. Define rotation/revocation, expiry, key compromise response and least-privilege access. Never copy `~/.codex`, `~/.gemini`, SSO cookies or browser profiles into model-running containers.
5. Positive provider probe (one bounded request) requires a separately authorized isolated runner, exact allowlist, quota and independent evidence.

## 5. Required test and acceptance gates

- **C02-D1 — DESIGN:** owner signs supported providers, service/data handling and budget, credentials/egress placement and exact boundaries. The resulting approved ADR follows repository governance; this draft is not that ADR.
- **C02-D2 — IMPLEMENTATION:** isolated inference brokers and credential-free executor exist; verify no secret can be read by arbitrary tool execution; quota/timeout/recovery tests are deterministic.
- **C02-D3 — VALIDATION:** independent Auditor returns strict `audit.schema.json` report; Host validator from Issue #43 checks exact `reviewed_scope` and valid status; missing review => BLOCKED.
- **WP-2 — NETWORK:** credential-free T01–T10 or equivalent security matrix in actual disposable runtime, no direct-bypass or fallback.
- **WP-3 — EVIDENCE:** Host records exact SHA/issue/run IDs, sanitized logs, deterministic offline Gateway/Node ESP-IDF v6.1 build/test and bounded repair fake fault paths.
- **WP-4 — PILOT:** human explicitly authorizes **one** supervised harmless Issue pilot only after G01–G08; maximum 1 repair; AWAIT_HUMAN; no Host Draft PR publisher needed for this pilot.

## 6. Stop conditions / status

**Current: DESIGN_DRAFT.** Identity entitlements, credentials, billing, external runtime and network isolation are **NOT_VERIFIED**. H01, H02, H03 and H04 stay open. If Codex CLI cannot be separated from arbitrary tool execution, don't bypass restrictions with a user-home auth mount. If Gemini API eligibility or cost is unavailable, STOP and seek an explicitly approved alternative, not consumer AGY account rotation.

Issue #43 validator code and CI are integrated into the Draft PR #38 branch; finding M02 security closure is still pending independent review. C01 provenance mismatch is recorded, not retroactively PASS.
