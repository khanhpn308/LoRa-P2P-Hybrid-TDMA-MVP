# Native Fast Lane quality gates

Issue [#88](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/88)
adds an offline, read-only local checker. It runs fixed Git inspection commands
and validates Host receipts. It never executes commands from a manifest, starts
Docker, obtains credentials, signs grants or changes GitHub policy. The
Coordinator selects reviewed local tests and collects their actual results.
This is a CLI plus agent instructions, not a Host daemon or merge enforcement.

For `Chạy Issue #N` and `Nghiệm thu PR #N`, the Coordinator runs the checker
before and after a fresh Auditor. The operator does not enter another command.
The PR review route stays read-only unless the operator authorizes fixes.
The examples below are for reproducing the Coordinator's checks.

```bash
python3 scripts/agent_harness/quality_gates.py --repo /path/to/candidate --base <trusted-base-sha> --fingerprint-only
python3 scripts/agent_harness/quality_gates.py --repo /path/to/candidate --base <trusted-base-sha>
python3 scripts/agent_harness/quality_gates.py --repo /path/to/candidate --base <trusted-base-sha> --evidence-dir /path/to/host-evidence --manifest manifest.json
python3 -m unittest discover -s tests/agent_harness -p test_quality_gates.py -v
```

Keep evidence outside the candidate worktree. A manifest inside the candidate
would change its own fingerprint. Run the checker from a trusted checkout,
particularly when reviewing a PR that changes the checker. Inspect candidate
Git configuration before running other tools. The checker disables fsmonitor,
external diffs and textconv for its Git commands. It blocks configured Git
clean/process filters before diff, including unused global filter configuration.
Use an inspected disposable checkout without those filters; do not weaken or
change a user checkout configuration automatically. Assume-unchanged and
skip-worktree index flags also block, because they can hide paths from routing.

Exit 0 means all selected automatic checks passed. Exit 1 means a selected check
failed or lacks evidence. Exit 2 means source/evidence inspection could not
complete and the result is `NOT_VERIFIED/BLOCKED`. An unselected rule is
`NOT_RUN` with a routing explanation. A selected rule with no receipt is
`NOT_RUN` and blocks automatic acceptance. Invalid, stale or incomplete evidence
is `NOT_VERIFIED` and also blocks. `OWNER_WAIVED` for GitHub Actions never waives
these local checks.

## Risk matrix and remediation

Routing uses the complete diff from the supplied base to the current worktree,
including committed changes and nonignored untracked files. Deletions and
renames retain their old paths in the diff. All selected rules are required.
Harness control paths are checked before the Markdown fast path. Changes to
any `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/`,
`.agents/`, `.agent-harness/`, `.codex/` or `scripts/agent_harness/` select both
`TOOLING-CHECK` and `SECURITY-CHECK`. The active control runbooks also select both:
`harness-fast-lane.md`, `harness-quality-gates.md`, `AI_TASK_START_PROTOCOL.md`,
`agent-harness-firmware.md` and `agy-supervised-pilot.md` under
`docs/development/`. These paths define execution, review or evidence policy,
regardless of their file extension. Missing receipts block automatic acceptance
and human security review remains pending.

Ordinary Markdown, including README files, development notes and architecture
documents, still selects only the common checks. A filename containing security
or MQTT does not make ordinary Markdown executable policy. Other paths use
these rules:

| Rule ID | Selection | Evidence for PASS | Failure or missing proof |
|---|---|---|---|
| `SECRET-SCAN` | Every candidate | Built-in scan of tracked/nonignored worktree files and index blobs | Remove credential material from worktree **and index**; rotate exposed credentials through the owner. Do not print them. |
| `DIFF-CHECK` | Every candidate | Actual `git diff --check <base>` exit 0 | Fix whitespace/conflict markers. Stage new files before the final check. |
| `FIRMWARE-CHECK` | `firmware/` implementation | Reviewed module tests/build receipts, exact ESP-IDF v6.1, relevant contracts | Missing compiler/HIL/RF evidence stays separate; never infer hardware PASS. |
| `BACKEND-CHECK` | `backend-go/` implementation | Applicable Go tests/build and contract receipts, correct pinned compiler | Scope and Draft Go Standard routing still apply. |
| `TOOLING-CHECK` | Harness control paths above, `scripts/`, `tests/agent_harness/`, workflow implementation | Targeted tests for the affected tool and its callers | Do not run candidate-provided shell commands without inspection. |
| `INFRA-CHECK` | `deploy/`, `tests/integration/`, `.env*`, Compose or MQTT/TLS/ACL paths | Local integration receipts including PostgreSQL health/persistence when affected | Docker unavailable is `NOT_VERIFIED`, never synthetic runtime PASS. |
| `SEC-KEY-MOUNT` | Same infrastructure/MQTT paths | Complete runtime expanded mount inventory, client isolation and source modes | Reject wrong identity/server/backend keys, writable mounts and unsafe permissions. Expand directory mounts; unresolved inventories cannot PASS. |
| `MQTT-ACL-PERM` | Same infrastructure/MQTT paths | Non-root broker UID/GID, readable matching ACL owner/group mode0600, complete startup logs | Fix ACL/image ownership and rebuild. Warnings, permissions/startup errors FAIL even with command exit 0. |
| `NET-LOOPBACK` | Same infrastructure/MQTT paths | All resolved bindings loopback, localhost success, non-loopback rejection with a successful control path in the same probe context | Fix exposed bindings. Missing control/context or WSL2-only proof for a LAN claim is `NOT_VERIFIED`. |
| `TLS-AUTH/ACL-NEGATIVE` | Same infrastructure/MQTT paths | Server verification, positive flow, wrong-cert and anonymous rejection, cross-Gateway publish and subscribe denial | Config diff or connection failure alone cannot certify TLS/ACL. |
| `SECURITY-CHECK` | Harness control paths above, credential/security/auth/crypto/checker paths, contracts or workflows | Reviewed risk-specific local security test receipt | Human review remains required; tests do not approve a security design. |

Synthetic `tests/agent_harness/` fixtures select tooling/security checks, even
when fixture names contain ACL or TLS. They do not select live infrastructure.
Infrastructure routing is deliberately conservative. For example, a deployment
Dockerfile change selects all infrastructure security rules. A reviewer can
narrow tests within the Host receipt with an explicit coverage justification,
but cannot mark a required runtime rule PASS without its observations. Update
the registry under a scoped Issue if new path conventions need different routing.

## Receipt contract

Every rule result contains `rule_id`, `status`, `severity`, `file:line`, `command`,
`exit_code`, `receipt_path`, `tool_version`, `source_sha` and `limitation`.
For runtime rules the location defaults to the first changed path, line 1,
as a candidate locator, not a precise diagnostic. Secret findings identify the
matched file/line. Commands from receipts appear as SHA256 digests to avoid
printing arguments that might contain credentials. The Host keeps the exact
reviewable command in its restricted manifest, with secret arguments redacted
at collection time. Do not pass secrets on command lines.

The candidate fingerprint includes base SHA, HEAD SHA, index modes/blob IDs,
tracked file hashes and nonignored untracked source hashes. Re-run after staging,
committing or changing files. Collect fresh receipts for a changed fingerprint.
A second inventory after checks detects source changes during execution.
Known credential paths block without reading their contents. Their bytes are
not fingerprinted because they must be removed before acceptance.

Use `--fingerprint-only` to obtain `source_sha` and `candidate_sha256` before
collecting evidence. It does **not** certify scan success. A Host manifest has
this form, repeated per required rule:

```json
{
  "checks": {
    "TLS-AUTH/ACL-NEGATIVE": {
      "source_sha": "<actual candidate HEAD SHA>",
      "candidate_sha256": "<actual candidate fingerprint>",
      "command": ["python3", "-m", "unittest", "discover", "-s", "tests/integration", "-v"],
      "exit_code": 0,
      "tool_version": "<actual Python, Docker, Compose and image versions>",
      "receipt_path": "infra-runtime.log",
      "receipt_sha256": "<SHA256 of actual log bytes>",
      "observations": {
        "runtime": true,
        "server_verified": true,
        "allowed_flow": true,
        "wrong_cert_rejected": true,
        "anonymous_rejected": true,
        "cross_gateway_publish_denied": true,
        "cross_gateway_subscribe_denied": true
      }
    }
  }
}
```

The Host derives observations from inspected test assertions and actual command
results, not model prose. Capture the direct process exit, not the exit of `tee`
or a shell `... || true`. Save sanitized logs and hash their exact bytes. Never
copy an observation from fixtures into a real manifest as if it were measured.
A hash proves byte consistency, not authorship. The manifest and observations
are trusted Host inputs. An agent can forge them; the CLI does not authenticate
the collector. Review the command, test source, log and observations together.

`tests/agent_harness/fixtures/quality_gates/safe.json` gives the complete
observation schemas. `unsafe.json` and `missing.json` exercise FAIL and
NOT_VERIFIED. `runtime.log` is explicitly synthetic. Regression tests construct
manifests around these fixtures in disposable directories, test the public
certificate case, and assert CLI exits. No private keys are supplied in Git.

Observation details:

- `SEC-KEY-MOUNT` requires `runtime_inventory_complete`, `clients` including
  anonymous, gw-a, gw-b and backend, and `broker.mounts`. Each mount has an
  absolute `source`, absolute `target`, `read_only` and `kind`. Expand runtime
  directory mounts into their verified visible files. Public certs use
  `public_certificate` and `.crt` or `.pem` paths; several CAs/certs are allowed.
  Private keys use `private_key`, matching `<identity>.key` source/target and
  an octal `mode`. Client keys require 0600. Broker server.key allows 0600/0640
  or owner-read-only equivalents. Verify actual source identities and mount
  inventory in the collector; basenames alone do not authenticate keys.
- `MQTT-ACL-PERM` requires `runtime`, `startup_logs_complete`, `broker_uid`,
  `broker_gid`, `acl_uid`, `acl_gid`, `acl_mode` and `acl_readable`. The log must
  include startup output for every affected broker. Expected TLS authentication
  denials are not ACL file startup errors.
- `NET-LOOPBACK` requires `runtime`, `inventory_complete`, `bindings`,
  `network_context`, `representative`, `non_loopback_address` and
  `control_reachable`. Each binding supplies `service`, `host_ip`,
  `localhost_reachable` and `non_loopback_reachable`. The Host must cover every
  published port/address family and specify the exact deployment claim. A Docker
  bridge IPv4 probe only supports that context. Physical LAN/Internet, IPv6,
  direct routing, firewalls and WSL2 forwarding require separate checks.
- Module, tooling, integration and risk-specific `SECURITY-CHECK` receipts
  require `checks_complete: true` only after the Host verifies applicable tests
  actually ran. A skipped unittest suite or incomplete coverage is not complete.
  The CLI cannot judge module coverage or compiler suitability from arbitrary
  log text. The reviewer must assess those receipts.

## Review and acceptance

Run gates before Auditor handoff. Preserve the exact candidate fingerprint,
manifest hash, receipt hashes and tool source SHA. Give the fresh Auditor a
read-only snapshot plus AC and evidence. Include `changes.patch` for the entire
PR base-to-HEAD diff, and a separate `remediation.patch` from the reviewed HEAD
when fixing review findings. Record each exact Git command, direct exit code,
base/head SHA and patch SHA256 in a Host patch manifest outside the worktree.
Hash the patch bytes with the source and log inventory, and compare that same
patch after Auditor review. Do not omit it from the Host evidence directory
just because a copy exists in the Auditor snapshot. Request a separate report on false
positives, filesystem reads and evidence integrity. After review, run gates
again and compare fingerprint, diff and evidence hashes. Any candidate or
evidence change invalidates that review. Fixes need fresh tests and review.

Report these dimensions separately:

- `AUTO_CHECK_PASS` means required deterministic checks have receipts and passed.
- `AUDIT_PASS` is the model's source/evidence verdict, with model/provider and
  filesystem/isolation limits disclosed. The checker itself returns audit
  `NOT_VERIFIED`; attach the fresh Auditor report separately.
- `HUMAN_SECURITY_REVIEW_PENDING` applies to infrastructure/MQTT, firmware and
  security-sensitive paths. Only a real authorized human reviewer can record
  `HUMAN_SECURITY_REVIEW_PASS`, with a review URL and exact reviewed SHA.

Any selected FAIL, missing required evidence or unresolved P0/P1 finding blocks
`READY_TO_MERGE`. Security-critical PRs also require human security review.
The CLI always returns `ready_to_merge: false`; it cannot certify human review
or authorize merges. Coordinator instructions enforce this stop operationally,
not through a GitHub branch rule. A Draft PR with findings is allowed and must
state `PARTIAL/BLOCKED` where acceptance is incomplete. Issue #16's Human
Security Audit cannot be replaced by a model audit or this tool.

The read-only checks allow only regular files under the chosen repository or
Host evidence root, reject symlink components and traversal, and bound reads to
8 MB/file and 64 MB total source/index bytes. Ignored/untracked local credentials
are not read. Known key/container/.env/secret paths are rejected before opening;
renamed files undergo bounded signature detection. Output never includes matched
credential values or Git stderr. This is a Linux CLI, not a hostile-process
sandbox. It does not scan all history or detect arbitrary encrypted/encoded
secrets. Private-key headers, selected token signatures, environment password
assignments and quoted credential literals are covered. Schema properties and
public certificates are allowed. Keep raw logs restricted and sanitized; avoid
plain Compose config and full container inspect output containing environment
variables.

## Issue #88 execution receipt, 2026-10-27

The Coordinator implemented directly, then requested a fresh native read-only
Auditor. This is the owner-selected fast lane, without signed MCP execution.
Base `6b49ba090589496553de444b747b5b1d090a7650`; Issue #88 exact allowed paths
are the checker, its new tests/fixtures, this document, the fast-lane SOP,
`AGENTS.md` and `.agents/agents/harness-coordinator.md`. No infrastructure,
firmware, backend, contract or workflow source was changed.

A disposable local clone of remediated PR #87 at
`5d50edbf01583100a7ab183ca05e17110b7c8f68` ran its inspected existing integration
suite. A one-off Host observer outside that clone wrapped successful test
assertions to collect runtime mount paths/modes, broker stat and network probe
results. It inspected Docker mount metadata and filesystem modes, never key
contents. No candidate source was modified. The full suite ran through
`python -u /tmp/issue-88-evidence/run_infra.py`, exit 0, with an outer 300-second
timeout and Python 3.12.3, Docker client/server 29.8.0 and Compose 5.5.1.
The test internally provisions disposable keys through its existing Docker
helper. This checker needs no root or Docker; that separate integration test
requires trusted Docker daemon access.

```text
PASS: Compose profiles, loopback-only bindings and dev network isolation
PASS: missing/empty PostgreSQL environment rejected
PASS: broker uid1883, ACL owner1883:1883 mode0600, server-only key mount; no ownership/startup warnings
PASS: each client sees only public CA and its own certificate/key; anonymous sees CA only
PASS: PostgreSQL healthcheck and persistence after container recreation
PASS: separate-network client reaches non-loopback control listener on 192.168.1.3
PASS: postgres reachable via localhost, rejected via non-loopback 192.168.1.3:44647
PASS: mqtt-dev reachable via localhost, rejected via non-loopback 192.168.1.3:44645
PASS: mqtt-tls reachable via localhost, rejected via non-loopback 192.168.1.3:44646
PASS: published TLS port verifies server CA and hostname
PASS: anonymous/no certificate rejected by TLS
PASS: untrusted certificate rejected by TLS
PASS: both Gateways and Backend exchange every allowlisted topic at MQTT5 QoS1
PASS: cross-Gateway writes, ClientID/username spoof, reversed roles, unknown CN and unlisted topic denied with PUBACK 135
PASS: cross-Gateway reads, wildcard leakage and Backend downlink reads deliver no messages
Ran 9 tests in 124.512s
OK
```

The automatic gate initially blocked for missing receipts. With the actual
Host manifest and logs it reports:

```text
SECRET-SCAN: PASS
DIFF-CHECK: PASS
FIRMWARE-CHECK: NOT_RUN
BACKEND-CHECK: NOT_RUN
TOOLING-CHECK: PASS
INFRA-CHECK: PASS
SEC-KEY-MOUNT: PASS
MQTT-ACL-PERM: PASS
NET-LOOPBACK: PASS
TLS-AUTH/ACL-NEGATIVE: PASS
SECURITY-CHECK: PASS
AUTO CHECKS: AUTO_CHECK_PASS
HUMAN SECURITY REVIEW: HUMAN_SECURITY_REVIEW_PENDING
READY_TO_MERGE: false
```

Firmware/backend rules were unselected. The secret/path scanner, targeted
infrastructure/tooling/security receipts and all four runtime security rules
passed. This reuses PR #87's actual tests; it does not remediate PR #87 or
replace Issue #16's human audit. The network claim is limited to IPv4 from the
separate Docker bridge to this Linux host. Physical LAN/Internet, IPv6 and WSL2
forwarding remain NOT_VERIFIED. Test resources and temporary keys were cleaned
by the integration suite.

A separate disposable docs-only Git fixture changed only README.md. The actual
CLI returned exit 0 and `AUTO_CHECK_PASS`, selected only common rules and did
not request Docker/module evidence. The regression suite also covers unsafe
and missing evidence for the five required rule IDs, public cert false positives,
staged/hidden secrets, warnings, symlinks, traversal, malformed receipts and
source/hash changes. Full harness tests passed, with exact final counts recorded
in the Draft PR.

Host artifacts are local execution evidence at `/tmp/issue-88-evidence/` and
may disappear when the workspace is removed. Their SHA256 values at collection:

```text
infra-runtime.log f00d5bd3d9c1e45ea99f7ad104a927b8a0e6614beb1f308a4bde15a252d93268
infra-manifest.json 3e4e4215a5f72237d6d09a695515942ceb63f4e9e18303cab5f3ff36feab06ef
infra-observations.json 5d17034dcdbd67475b78d06b0f9e54f82b79de5f9eda18ac8d1aad7accb692d4
run_infra.py 85ccfd360dbb7bb293b28af5ef781dc2fe49acf4b2b7839e155ed6f63d06c3a4
docs-report.json 7cdf666721d3b67aaf34e9a6dba48561f22d8bcd0fe99b1ef94140344186bb3e
candidate_sha256 b796b789ff6d5b4a4360d70d834faee0cc55df4e5799ca1ff720803ce2950ed5
```

These hashes allow local integrity comparison, not recovery of missing logs or
proof of collector authorship. Review the Host artifacts or rerun the inspected
integration test before relying on runtime claims in another environment.
CodeGraph MCP and CLI were unavailable, `NOT_RUN`. GitHub Actions acceptance
remains `OWNER_WAIVED`, with no CI_PASS claim. RF/HIL/timing were not tested.

## PR #89 policy-routing remediation

The original routing returned early for every `.md` file. A change limited to
`AGENTS.md`, the Coordinator specification or an active Harness runbook could
therefore report automatic PASS without tooling/security receipts. Control
paths now take precedence over the ordinary Markdown rule. Regressions exercise
the control path families, tracked staged/unstaged policy-only CLI changes and
ordinary documentation. The CLI must block policy-only changes with missing
receipts while preserving docs-only automatic PASS without Docker evidence.

The original `changes.patch` was present in the final Auditor snapshot but
missing from `/tmp/issue-88-evidence/`. The remediation restores that historical
artifact by reproducing the original Git diff and comparing its hash to the
original snapshot. New full-PR and remediation patches, command/exit/SHA
receipts, complete Harness test logs, final-HEAD gate reports and fresh Auditor
report are collected in `/tmp/issue-89-remediation/`. The updated Draft PR
records exact final counts, HEAD and hashes. These workspace-local artifacts
can expire; their hashes are integrity evidence, not a substitute for the bytes
or authenticated Host collection. Previous Docker execution remains historical
unless explicitly rerun; validating its receipts with a new runner is reported
separately from executing Docker tests again.
