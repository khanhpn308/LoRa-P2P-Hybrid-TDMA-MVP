# Normative PR Review Runbook & Human Merge Policy

## 1. Overview and Authority
The **`Nghiệm thu PR #N`** command triggers an automated, deterministic, and strictly **read-only** evaluation of pull requests against project standards, architecture contracts, and verification gates before human merge.

> [!IMPORTANT]
> **Non-auto-merge policy:** This Harness operates in read-only mode and **NEVER merges pull requests automatically**, self-approves, or disables GitHub branch protections. Human specialist sign-off is mandatory.

## 2. Operator Workflow (`Nghiệm thu PR #N`)

```bash
# 1. Enforce mandatory Host G0 context on tracked AGENTS.md
python3 scripts/agent_harness/agent_context.py --repo .

# 2. Export frozen Auditor context and evidence bundle (for native invoke_subagent)
python3 scripts/agent_harness/pr_review.py --pr <PR_NUMBER> --export-auditor-context /tmp/harness-evidence-pr-<N>/auditor_context.json --evidence-dir /tmp/harness-evidence-pr-<N>

# 3. Autonomous review with fresh native Auditor (spawns agy sandbox)
python3 scripts/agent_harness/pr_review.py --pr <PR_NUMBER> --auto-audit --evidence-dir /tmp/harness-evidence-pr-<N>

# 4. Review with pre-generated Auditor report
python3 scripts/agent_harness/pr_review.py --pr <PR_NUMBER> --auditor-report /tmp/harness-evidence-pr-<N>/auditor_report.json --evidence-dir /tmp/harness-evidence-pr-<N>

# 5. (Optional) Publish review report to PR comment (requires explicit operator authorization)
python3 scripts/agent_harness/pr_review.py --pr <PR_NUMBER> --auditor-report /tmp/harness-evidence-pr-<N>/auditor_report.json --publish-comment
```

For offline or synthetic validation without GitHub API access:
```bash
python3 scripts/agent_harness/pr_review.py --fixture tests/agent_harness/fixtures/pr_review/pr_clean_docs.json
```

## 3. Evaluation Gates (PR-01 through PR-08)

1. **`PR-01 GOVERNANCE`**:
   - Matching OPEN Issue with clear acceptance criteria.
   - Changed paths strictly within declared `Target Directories (allowed paths)`.
   - Branch naming convention (`feature/*`, `fix/*`, `docs/*`, `chore/*`, `research/*`).
   - CODEOWNERS mapping and author independence (author self-approval is rejected).

2. **`PR-02 ARCHITECTURE/CONTRACT`**:
   - Guarded versioned contracts (`contracts/**`), ADRs, and architecture docs.
   - Requires specialist human sign-off from both producer and consumer code owners.

3. **`PR-03 RULE-ID`**:
   - Selective Rule-ID routing via `#137` Standards Router.
   - Firmware C changes load C Coding Standard v2; Backend changes load Go Standard v2; Docs load minimal docs rules. Never loads full unselected standard.
   - Fail-closed: Router errors or malformed receipts result in `BLOCKED/NOT_VERIFIED`, never fake fallback rules.
   - Mandatory rules: Any changes touching `backend-go/**/*_test.go` must include `TS-001`.
   - Binding: Rule selection source commit must match the PR HEAD SHA.

4. **`PR-04 CORRECTNESS`**:
   - Checks for git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`), truncated patches, or corrupted diffs.
   - **Full-diff batching & zero silent truncation**: Prompts never silently truncate diffs. Diffs exceeding batch thresholds (`MAX_BATCH_DIFF_BYTES = 60_000`) are partitioned into file/hunk batches with batch index, batch diff SHA-256, overall diff SHA-256, and 100% hunk preservation (`extract_diff_hunks`).
   - **Mandatory 100% path & batch coverage**: The union of reviewed paths across batches must exactly match all changed files, and all expected batches must be accounted for; any omission fails closed with `AUDIT-COVERAGE-MISMATCH`.
   - **Cryptographic snapshot binding & anti-fabrication defense**: Auditor reports are bound to frozen PR metadata (`base_sha`, `head_sha`, `diff_sha256`, and per-rule `diff.patch` receipt hash). Absent or malformed fields, mismatched commit hashes, or fabricated wrapper envelopes (conflicting outer vs inner snapshot metadata) fail closed with `AUDIT-SNAPSHOT-MISMATCH`.
   - Evaluates unresolved high-severity findings from fresh read-only Auditor; requires full per-ID coverage.

5. **`PR-05 SECURITY`**:
   - Automated secret scanning across all diff patches for credentials, tokens, and private keys.
   - Specialist security review boundary strictly exempts synthetic test fixtures (`/fixtures/`) while enforcing review for real security test code and cryptographic contracts.
   - Prompt-injection defense: PR body, title, and comments are treated strictly as untrusted data, never instructions.

6. **`PR-06 TESTING`**:
   - Commit check-runs evaluated for HEAD commit.
   - Any failure blocks acceptance; in-progress checks return `NOT_VERIFIED`.

7. **`PR-07 RF/HIL`**:
   - Mandatory for RF stack, SX1276 driver, MAC timing, or hardware changes.
   - Requires Hardware-in-the-Loop (HIL) test receipt and human RF specialist review.
   - Explicitly marked `NOT_APPLICABLE` for docs and backend changes.

8. **`PR-08 MERGE-INTEGRITY`**:
   - Pre- and post-review HEAD and BASE SHA check: re-queried immediately before policy evaluation and comment publishing; any commit push or base rebase during review or model audit fails closed with `STALE_REVIEW/BLOCKED` (dual TOCTOU race protection).
   - Unresolved review comment threads or outstanding `CHANGES_REQUESTED` block readiness.
   - Branch protection and rulesets visibility recorded (`MERGE_PROTECTION_NOT_VERIFIED` if unconfigured).

## 4. Risk Classification & Proposed Approval Policy

| Risk Level | Path Criteria | Proposed Human Approval Requirement |
| :--- | :--- | :--- |
| **LOW** | Documentation, markdown, templates | >= 1 independent human reviewer |
| **MEDIUM** | Backend Go logic, ordinary utilities, non-RF firmware, unit tests | >= 1 relevant component owner / peer reviewer |
| **HIGH** | RF stack, SX1276 driver, TDMA MAC, ISR/timer, crypto/contracts, harness controls | >= 2 specialist human approvals with relevant disciplines |

## 5. Host Verdicts & Independent Dimensions

The Policy Evaluator emits exactly ONE of:
- **`READY_FOR_HUMAN_REVIEW`**: All automated checks passed; ready for human peer review. Crucially, `ready_to_merge` remains `false`.
- **`CHANGES_REQUESTED`**: CI test failures, open review threads, or auditor defect findings.
- **`BLOCKED`**: Hard blockers (scope violation, secrets, prompt injection, TOCTOU SHA race, missing HIL, unapproved contract changes).
- **`NOT_VERIFIED`**: Missing check-run receipts, checks in progress, or auditor unverified.

Independent evidence dimensions preserved in report:
- `AUTO_CHECK_PASS`: Boolean status of PR-01, 03, 05, 06, 07.
- `SECRET_SCAN_PASS`: `PASS` or `FAIL` (basic diff pattern scan).
- `SECURITY_REVIEW_PASS`: `PASS`, `NOT_APPLICABLE`, or `NOT_VERIFIED` (independent specialist sign-off; never inferred from regex scan alone).
- `AI_REVIEW_PASS`: `PASS`, `FAIL`, or `NOT_VERIFIED` (fresh read-only Auditor; author self-audits are rejected).
- `HUMAN_APPROVED`: `APPROVED` or `PENDING` based on valid approvals.
- `HIL_RF_PASS`: `PASS`, `FAIL`, `NOT_APPLICABLE`, or `NOT_RUN`.
- `MERGE_ENFORCEMENT_ACTIVE`: `ENFORCED` or `NOT_VERIFIED`.
