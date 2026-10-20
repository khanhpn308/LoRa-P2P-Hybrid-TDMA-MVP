# Pre-Task-Breakdown Readiness — Hybrid TDMA Monorepo

**Status:** PARTIAL_WITH_FINDINGS. Owner: Project Lead. Branch: `research/ready-for-taskbreakdown`.

This checklist is a prerequisite to generating team tasks and AI work orders. It does **not** assert that the RF, MAC, security or latency requirements are fulfilled.

## A. Firmware shared-component discovery

The following lines must appear in **both**:
- `firmware/gateway_master/CMakeLists.txt`
- `firmware/sensor_node/CMakeLists.txt`

```cmake
set(EXTRA_COMPONENT_DIRS "../components")
```

Four planned shared components are:
`sx1276_driver`, `lora_mac`, `tdma_common`, `airtime_policy`.

**Critical distinction:** The CMake variable identifies a search directory, but `firmware/components/*/` currently holds scaffold READMEs only. ESP-IDF will treat each as a buildable component **only after it has a valid component `CMakeLists.txt` plus registered source/include files**. Therefore, initial firmware tasks must create their minimal component manifests, real sources/tests and prove **both** Gateway and Node `idf.py build`. No fake empty implementation, no premature HIL/PHY PASS claim.

## B. Gate field — exact seven GitHub Projects options

Project: https://github.com/users/khanhpn308/projects/1

Create a **single-select Custom Field named `Gate`**, matching this exact mapping (not seven GitHub Labels):

| Option string | Purpose | Source gate |
|---|---|---|
| `G0: Scope` | Baseline requirements, ownership and RTM | G0 |
| `G1: RF` | RF, airtime and legal feasibility | G1 |
| `G2: Protocol` | MAC, TDMA, security design, vectors | G2 |
| `G3: Embedded` | ESP-IDF Gateway/Node behavior and HIL | G3 |
| `G4: Integration` | MQTT, Go, PostgreSQL, client interfaces | G4 |
| `G5: Security/Reliability` | Threat model, failures, soak tests | G5 |
| `G6: Pilot Acceptance` | Field tests and approval | G6 |

To inspect or create the field **using credentials belonging to the Project owner**:

```bash
gh auth status
gh auth refresh -s project      # only if Project scope is missing
bash scripts/setup_project_gate.sh
gh project field-list 1 --owner khanhpn308 --format json
```

The script **checks for an existing `Gate` field first**. If the options do not match, it stops instead of overwriting or deleting data. Do not report this field as CREATED/VERIFIED unless the command succeeds on the live Project or the project owner confirms it in the UI.

Each task's Project Gate value must be set to one of these seven options; gate completion remains controlled by evidence in `docs/verification/acceptance-gates.md`.

## C. CODEOWNERS — invitation dependency

File: `.github/CODEOWNERS`. It currently uses `@khanhpn308` as a *valid temporary owner* on all path groups. Do **not** invent usernames or replace these entries with unaccepted collaborator handles.

Once all five other members accept invitations and have repository permissions:
1. Confirm each GitHub username exactly (profile URL + access permission).
2. Assign real owners to Firmware common, Gateway, Node, Go, Infrastructure, Web, Mobile, Contracts, Docs and Tests, allowing some people to cover multiple paths.
3. Edit `.github/CODEOWNERS` by reviewable PR; the user listed for each path must have valid repository access.
4. For `contracts/` and timing/security-critical changes, include reviewer(s) for all affected producer/consumer interfaces.
5. Enable CODEOWNERS/PR reviewer enforcement using the repository's available ruleset/branch protection. A CODEOWNERS file alone does not enforce approvals.

**Blocking dependency:** Actual five accepted usernames are not currently in the architecture documents. This remains `PENDING_TEAM_IDENTITIES`; it cannot be completed automatically merely by waiting.

## D. Path-Scoped Issue Policy (mandatory from now on)

Every Task, Research or Bug Issue must include a required field **`Target Directories (allowed paths)`**.

```markdown
### Target Directories (allowed paths)
- firmware/components/sx1276_driver/
- tests/hil/

### Out of Scope
- firmware/sensor_node/ (unless explicitly added to this Issue)
- backend-go/
```

Rules:
- Use **repository-root-relative explicit paths**. Include related test, doc, migration or contract paths up front when genuinely necessary.
- The owner/AI may edit **only** the listed paths. No repo-wide formatter/refactor without explicit approval.
- If another directory must change, **update the Issue scope first** and request cross-team owner approval before editing. Comments alone are not a silent permission grant.
- PR template repeats Target Directories and reviewers compare `Files changed` to the approved Issue scope.
- Path-Scoped Issues are enforced as a *documented workflow + required Issue Forms + human PR review*. No automated GitHub rule currently proves that every changed file matches the Issue's allowed paths.

The five Issue Forms under `.github/ISSUE_TEMPLATE/` contain the required field. For manually authored Issues or AI-created Issues, the same section is **mandatory**.

## E. Readiness status and verification

| Check | Current assessment | Closure evidence |
|---|---|---|
| CMake EXTRA_COMPONENT_DIRS (both projects) | PRESENT | File diff + CI structure check |
| Four fully buildable shared libraries | **NOT_IMPLEMENTED** | Component CMakeLists, source, dual idf.py build |
| Gate field G0–G6 on live GitHub Project | **NOT_VERIFIED** | gh output or Project UI screenshot |
| CODEOWNERS fallback mapping | PRESENT | Reviewed file |
| Five accepted team usernames in CODEOWNERS | **PENDING_TEAM_IDENTITIES** | Accepted collaborators + reviewed owner mapping |
| Path-Scoped Issue Forms (five) | PREPARED | Repo YAML + GitHub Issue Form UI |
| PR/AI scope policies | PREPARED | Policy diff + owner approval |

Proceed to Task Breakdown only with open prerequisites called out. The first firmware initialization Issue must test the shared ESP-IDF component discovery; creating an entire protocol is **not** implied by a successful scaffold build.
