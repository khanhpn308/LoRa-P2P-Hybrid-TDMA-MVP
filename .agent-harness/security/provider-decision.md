# P1-B2 C02 — Operator-invoked Antigravity CLI Gemini Auditor

**Status: DESIGN_DRAFT / USER-PREFERRED AUDITOR PATH, NOT LIVE-AUTHORIZED.** Tracked by [Issue #45](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/45), stacked on [Draft PR #38](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/38). The user selected **Gemini via the official Antigravity CLI (`agy`)**, explicitly **not Gemini API Auditor**. This revision changes **design docs only**; no auth, runtime, provider request, network or firmware actions.

## 1. Official interface and use boundary (source snapshot: 2026-10-23)

- Official [Headless CLI](https://www.antigravity.google/docs/cli/headless/) documents the `agy -p` direct user invocation with `--output-format json`, `--json-schema`, `--model`, `--sandbox` and `--print-timeout`. The accepted JSON envelope includes `status`, `structured_output` and permission diagnostics on stderr. `--json-schema` guides provider output; Host must still independently validate it.
- Official [Antigravity FAQ](https://www.antigravity.google/docs/faq/) says **direct CLI scripting/CI is supported** but **wrapping consumer-login `agy -p` in a third-party coding agent/application or automating account rotation is not supported under consumer plans**. Being the genuine `agy` binary called by a subprocess does not automatically make third-party agent orchestration authorized.
- Consequently **do not wire consumer-authenticated `agy` into the Harness automatic Worker→Auditor callback**, do not route Codex prompts through it, and do not treat the prior `READ_ONLY_MODEL_PROBE_PASS_ONLY` as provider entitlement or production isolation evidence.
- For a genuinely fully unattended Worker→Auditor loop using `agy`, obtain explicit supported **Enterprise/provider authorization for this exact integration**; otherwise leave the automatic Auditor stage BLOCKED. This document does not substitute an API key or silently switch to Gemini API.

## 2. Minimal supervised audit handoff — selected proposal

| Stage | Responsibility | Boundary |
|---|---|---|
| Codex Worker | Writes an Issue-scoped candidate in disposable credential-free executor | Never receives AGY auth profiles, provider tokens, host socket, or unrestricted network |
| Trusted Host | Validates exact Issue scope/source SHA; runs deterministic/offline ESP-IDF v6.1 build, holds immutable review snapshot and output manifest | Does **not** invoke consumer-authenticated AGY as automated third-party backend |
| Human operator | Starts one fresh official `agy` headless CLI session as a **direct**, separately controlled audit task | Dedicated approved CLI login/profile; separate read-only immutable snapshot; no Worker writable files |
| Gemini via Antigravity CLI | Performs read-only independent code review and returns structured report | Pin the locally available Gemini slug using `agy models`; no `--continue`, no tool approvals or shell/write privileges |
| Trusted Host | Receives the operator-transferred structured JSON audit artifact; rejects wrong SHA, unknown scope, malformed envelope, duplicate keys, FAIL/INCONCLUSIVE | Shared strict Host parser/validator from Issue #43; no model output can authorize actions |
| Human | Reviews candidate, build and audit evidence | Stop at `AWAIT_HUMAN`; no auto PR publisher, merge, flash or RF |

This is a **split, operator-supervised pilot**, *not* the previously targeted fully autonomous E2E loop. The human action must be explicit and traceable for each AGY invocation; labeling it `AUTONOMOUS_AUDIT_PASS` is prohibited.

## 3. CLI audit safety checklist (design; do not execute in this Issue)

1. Use the **official `agy` binary** in a separate operator-controlled CLI environment. Approve identity entitlement and review vendor terms for actual use. No account sharing/rotation, token extraction or copying normal `~/.gemini`, SSO/browser cookies into Worker environments.
2. Host emits immutable/read-only, bounded snapshot and expected changed paths, source/candidate SHA, report schema SHA, and a short audit prompt. Ensure *read-only filesystem enforcement*; `--sandbox` and a read-only prompt **alone are not isolation boundaries**.
3. Operator selects an actual Gemini model slug shown by `agy models` and explicitly runs a **fresh headless** audit (`agy -p ... --model <verified-slug> --output-format json --json-schema <trusted-schema-file> --sandbox --print-timeout <bounded-duration>`). Use the direct CLI surface, **not** a Harness/third-party subprocess wrapper. Do not pass `--dangerously-skip-permissions` or grant shell/write tool permissions.
4. Capture stdout/stderr into a restricted evidence location with size/time budgets and redaction; never post raw session details, profile files or potential secrets in Issue/PR. A successful exit or `status=SUCCESS` is not enough.
5. Operator transfers only the reviewed sanitized report and receipt into trusted Host validation; Host checks signature/identity where available, exact snapshot/source SHA and `reviewed_scope`, strict JSON/schema, permission denial, and exact candidate fingerprint. Lacking verifiable binding => BLOCKED/NOT_VERIFIED; do not invent signed provenance.
6. PASS with empty findings/limitations may advance to the **human** gate only if deterministic Host build/tests and security controls passed. A FAIL or INCONCLUSIVE cannot be promoted into PASS. Repair (at most one) requires a new candidate SHA and a fresh, independently invoked AGY review.
7. If a full autonomous E2E is mandated, **STOP** here and request provider-supported authorization for programmatic `agy` orchestration. Do not emulate official permission by hiding invocations inside shell wrappers.

## 4. Mandatory credentials/runtime/network controls

- Authenticated AGY runs belong to an operator-controlled audit environment, never the arbitrary Worker or Build process. No shared writable profile mounts, host personal home, GitHub write tokens, or Docker socket. If dedicated auth isolation cannot be verified, BLOCK.
- The code executor is a disposable non-root VM/runner, without inference secrets; outbound access is externally denied and independently tested. Docker `Internal=true` and `HTTP_PROXY` alone are not proofs of egress restrictions.
- Host produces bounded SHA-linked receipts for approved Issue/body, source, candidate, offline build and review. Reject TOCTOU modification, unapproved file changes, malformed/oversized audit or permission soft-denials.
- Do not reuse or re-run historical AGY smoke as proof of live Worker→Auditor integration. The new workflow requires separate evidence and an operator approval for the actual model/quota use.

## 5. MVP acceptance and limitations

- **Design decision requested:** `AUDITOR_PROVIDER=AGY_CLI_GEMINI`, `AUDIT_INVOCATION=OPERATOR_DIRECT`, `AUDIT_INTEGRATION=AUTO_DISABLED_ON_CONSUMER_PLAN`, `GEMINI_API_KEY_REQUIRED=NO`. These are design choices, **not secrets or runnable configuration**.
- Issue #45 acceptance: independent operator audit procedure approved; exact handoff and Host schema validation planned; supported `agy` model/version and account eligibility checked at execution time; per-run quota and evidence constraints approved.
- WP-2 still needs isolated Worker, credential-free network T01–T10 verification, process/quotas; WP-3 still needs real offline Gateway/Node build receipts and fail-closed recovery; WP-4 requires G01–G08 and **one explicit pilot authorization**.
- **FULL_AUTONOMOUS_E2E: BLOCKED** under consumer-authenticated `agy` in third-party Harness. **SUPERVISED_HUMAN_HANDOFF: PROPOSED**, not verified by this documentation-only change.
- H01/H02/H03/H04 remain open; Issue #43 Host validator source/CI is integrated into PR #38's head but M02 independent security review is still pending. M01 scope history is disclosed, not retroactively PASS.

## 6. Stop conditions

No operator entitlement evidence; runtime not truly read-only; CLI would require dangerous permission bypass; arbitrary code receives AGY credentials; automatic Harness↔consumer AGY invocation; extra/missing audit scope; candidate SHA drift; no independent review; unapproved provider quota/network adjustments; firmware/contracts changes. Report BLOCKED; do not implement silent API fallback.
