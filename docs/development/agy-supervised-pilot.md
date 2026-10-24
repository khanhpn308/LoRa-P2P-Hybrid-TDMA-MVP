> **ARCHIVED PROCEDURAL RECORD FOR ISSUE #47 (not a new execution authorization).**
> The original Issue #47 branch has already been merged into an intermediate
> branch; the fixture README is included as historical evidence in the
> Issue #54 integration. The steps below describe the operator's original
> **one-time pilot**, where README was initially untracked; **do not rerun
> against main or recreate the fixture**. For a new coding Issue, obtain a
> new exact allowlist, clean branch, current source SHA, and fresh approval.
> The historical local AGY/Host evidence was reported by the operator, not
> independently reproduced by CI. No consumer-login AGY automation, model
> credential changes, live E2E, or RF work is authorized by this file.
>
# Issue #47 — Supervised Gemini Worker + Gemini Auditor via `agy`

**Status: PREPARED / OPERATOR EXECUTION NOT_VERIFIED.** This document is an
operator procedure, **not an autonomous Harness executor**. Source branch:
`docs/47-dual-agy-supervised-pilot` based on
`fix/34-harness-provider-proxy-gate`.
[Issue #47](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/47)
allows the Worker to modify **only**
`tests/agent_harness/fixtures/security_pilot/README.md`.
The four other allowlisted paths are Host-authored documentation in this PR.

## A. Prepare on an operator-controlled WSL2 checkout

Use your existing local repository (do not clone using another account). The
following commands are for **you to execute**, not commands run by the Harness:

```bash
git fetch origin
git switch docs/47-dual-agy-supervised-pilot
git pull --ff-only origin docs/47-dual-agy-supervised-pilot
git status --short
git rev-parse HEAD
agy --version
agy models
```

STOP unless the branch is exactly the Issue #47 branch and the working tree is
clean. Note the full source HEAD SHA and the chosen Gemini model name as
actually reported by your installed `agy`. Do not guess a model slug or use
`--dangerously-skip-permissions`, auto-approval/Turbo, copied auth profiles
or `--continue`. The toolchain version `firmware/esp-idf-version.txt` is
approved as `v6.1`; do not switch it.

## B. Worker — first, operator-direct Gemini CLI session

From **the clean Issue branch**, manually start the official interactive CLI:

```bash
agy
```

At the AGY prompt paste this task (human-provided, not dispatched by Harness):

> Gemini Worker for GitHub Issue #47. Create ONLY
> `tests/agent_harness/fixtures/security_pilot/README.md` with a short
> Markdown description saying this is a harmless supervised Harness fixture,
> that Worker and Auditor are separate Gemini/AGY CLI sessions, and that
> firmware/RF/HIL are untouched and NOT_VERIFIED. Do not edit any other file,
> run network/package-manager/Git write commands, create PRs, or change
> credentials. Report exactly which file you changed, then STOP. Request
> operator approval for each proposed command or file action.

Exit the Worker session after verifying the requested README exists.
If permission demands expanding scope, STOP instead of approving.

## C. Host diff gate — before any Auditor

```bash
git status --short
git diff --name-only HEAD
git ls-files --others --exclude-standard
git diff --check
python3 -m unittest discover -s tests/agent_harness -v
```

**Expected changed path (exactly one):**
`tests/agent_harness/fixtures/security_pilot/README.md`.
Because it is initially untracked, **`git diff --name-only` alone is
insufficient**; include `git ls-files --others`. Reject unknown paths,
symlinks, binary content, suspicious credentials and unexpected actions.
Record Host test stdout/stderr, return codes, candidate file SHA and HEAD
locally in an access-controlled location. No CI label or model narrative
substitutes for those artifacts. For this harmless README change, existing
Harness Python tests are the focused deterministic check; **both ESP-IDF v6.1
builds remain NOT_VERIFIED until actually executed** on that exact candidate.
Do not flash or transmit RF.

## D. Freeze independent review snapshot (operator)

The example copies only the single harmless changed file and committed audit
schema, not your Git credentials or Worker chat. These commands create a
separate **non-writable-by-default convenience copy**; `chmod` is not a
security boundary against the same user. For an enforced read-only mount,
use separately reviewed OS/VM controls.

```bash
REPO="$(pwd)"
AUDIT_PATH="tests/agent_harness/fixtures/security_pilot/README.md"
EVIDENCE="$(mktemp -d)"
SNAPSHOT="$(mktemp -d)"
mkdir -p "$SNAPSHOT/$(dirname "$AUDIT_PATH")"
install -m 0444 "$REPO/$AUDIT_PATH" "$SNAPSHOT/$AUDIT_PATH"
install -m 0444 "$REPO/scripts/agent_harness/adapters/audit.schema.json" "$SNAPSHOT/audit.schema.json"
sha256sum "$REPO/$AUDIT_PATH" | tee "$EVIDENCE/candidate-before.sha256"
sha256sum "$SNAPSHOT/$AUDIT_PATH" | tee "$EVIDENCE/snapshot.sha256"
git rev-parse HEAD > "$EVIDENCE/source-head.txt"
printf '%s\n' "$SNAPSHOT" > "$EVIDENCE/snapshot-dir.txt"
```

Verify the two file digest values match. Never copy `.git`, provider auth
profiles, keys, or tokens into `$SNAPSHOT`.

## E. Auditor — independent fresh AGY CLI session

**Manually** start the second official `agy` invocation from the snapshot.
This is a *separately operator-invoked direct CLI task*, not a subprocess
wrapped by the coding Harness. Select the actual Gemini model with
`agy models` first if a pin is required. Use a **fresh** session, not
`--continue` or the Worker's conversation:

```bash
cd "$SNAPSHOT"
agy -p 'Review ONLY tests/agent_harness/fixtures/security_pilot/README.md for Issue #47. Do not edit or run commands. Return JSON using the supplied schema. Use status PASS only with zero findings/limitations and reviewed_scope exactly ["tests/agent_harness/fixtures/security_pilot/README.md"]; otherwise FAIL or INCONCLUSIVE.' \
  --output-format json --json-schema "$SNAPSHOT/audit.schema.json" \
  --sandbox --print-timeout 10m \
  > "$EVIDENCE/agy-auditor.stdout.json" 2> "$EVIDENCE/agy-auditor.stderr.txt"
AGY_EXIT=$?
printf '%s\n' "$AGY_EXIT" > "$EVIDENCE/agy-auditor.exit-code.txt"
cd "$REPO"
```

This example **does not** grant broad tool approvals. If your CLI version
cannot honor requested restrictions or returns a permission denial, STOP.
Capture `AGY_EXIT` even when nonzero; do not treat exit 0 as sufficient.
Keep evidence local and sanitized. The audit snapshot must not be modified.

## F. Strict Host validation and human decision

This command uses the **existing** shared strict Host parser from Issue #43
without invoking the provider. It validates output shape/denials/scope, but
does **not** cryptographically authenticate the operator or prove the Auditor
saw the current candidate. Check digests manually as part of the handoff:

```bash
sha256sum "$REPO/$AUDIT_PATH" | tee "$EVIDENCE/candidate-after.sha256"
sha256sum "$SNAPSHOT/$AUDIT_PATH" | tee "$EVIDENCE/snapshot-after.sha256"
python3 - "$REPO" "$EVIDENCE" "$AUDIT_PATH" <<'PY'
import pathlib
import sys
repo, evidence, path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(repo / "scripts" / "agent_harness"))
from adapters.antigravity import parse_result, AuditError
import hashlib
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
snapshot = pathlib.Path(evidence / "snapshot.sha256")
original = sha(repo / path)
snapshot_copy = sha(pathlib.Path((evidence / "snapshot-dir.txt").read_text().strip()) / path) if (evidence / "snapshot-dir.txt").exists() else None
if snapshot_copy is None or original != snapshot_copy:
    raise SystemExit("BLOCKED: missing snapshot receipt or candidate SHA drift")
p = evidence / "agy-auditor.stdout.json"
if p.stat().st_size > 160000:
    raise SystemExit("BLOCKED: oversized AGY output")
report = parse_result(
    int((evidence / "agy-auditor.exit-code.txt").read_text().strip()),
    p.read_text(), (evidence / "agy-auditor.stderr.txt").read_text(),
    {path},
)
print("AUDIT_REPORT_SCHEMA_VALID_ONLY:", report["status"])
print("BUILD/RF/HIL/SECURITY: NOT_VERIFIED")
PY
```

The snapshot path is captured in Section D. **Do not call `AUDIT_PASS` on a schema-valid record alone**; Host checks and
independent human review remain separate.

One review cycle only. If review FAILS, capture the findings and request
separate human authorization for a single Worker repair on the same scoped
file, followed by a **new** fresh audit. INCONCLUSIVE or failed gates
remain BLOCKED; no automatic retry. Final state `AWAIT_HUMAN` is an
operator decision, not an autonomous Harness success.

## G. Exit checklist / no-go

- Exact only README change; source HEAD, candidate and snapshot digests stable
- Focused Python tests run with actual exit code and redacted log
- AGY Worker and Auditor sessions each evidenced as **operator direct**;
  Auditor separate context, no shared Worker writable tree
- Strict `status=SUCCESS`, valid `structured_output`, exact
  `reviewed_scope`; tool denials/timeout => BLOCKED
- No auto PR, commit, merge, flash, RF or contract changes
- Credential-free isolation was deferred, remains NOT_VERIFIED; therefore
  **FULL AUTONOMOUS E2E = NO-GO**
