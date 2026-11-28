# Harness V2.0 — Controlled Improvement Experiment Log (OD-10)

**Issue:** [#443](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/443) (`[Harness V2][P08-D]`) · **Baseline Revision:** `500acba0eb834e5f8c8daf7ec46142ec25a12798`
**Authoritative Spec & Plan:** [HARNESS_SPEC.md §6.6](HARNESS_SPEC.md#66-fleet-orchestration-and-meta-improvement) · [HARNESS_MASTER_PLAN.md §11](HARNESS_MASTER_PLAN.md#11-p08--orchestrator-multi-round-maker-checker--improvement-pilot) · [HARNESS_BASELINE_REPORT.md §7](phase-01/HARNESS_BASELINE_REPORT.md#7-wp-f--benchmark-protocol--metric-specifications-harness_specmd-73--od-06)
**Controller & Journal:** [`scripts/agent_harness/improvement.py`](../../scripts/agent_harness/improvement.py) · [`scripts/agent_harness/p1/state.py`](../../scripts/agent_harness/p1/state.py) (`improvement_experiments`, `improvement_events`) · [`tests/agent_harness/fixtures/improvement/`](../../tests/agent_harness/fixtures/improvement/controlled_experiment_scenarios.json)

> [!IMPORTANT]
> **Honest Status & Anti-Goodhart Boundary (`H2-FBK-10` / `H2-FBK-11` / `OD-10`):**
> - No live-provider productivity improvement is claimed here (`live_provider_evaluation: NOT_VERIFIED`, `human_rubric_calibration: NOT_VERIFIED`).
> - Baseline `#424` (`SECRET-SCAN` false positive) and `rf_tracker.go` `gofmt` drift remain unresolved on `main` and block real repository acceptance; `KEEP` on controlled fixtures demonstrates deterministic routing only (`FIXTURE_ONLY_NOT_PROMOTABLE`).
> - `KEEP` is strictly an experiment recommendation, never autonomous merge or deployment to `main`.

---

## 1. Frozen OD-10 Experiment Protocol

1. **Failure Attribution & Single Hypothesis:** Every experiment attributes a failure or metric gap via [`attribute_failure_from_journal`](../../scripts/agent_harness/improvement.py) (`observability.diagnose_failures`) and proposes **one** testable hypothesis (`one_change_summary`) over explicit, non-protected `allowed_paths`.
2. **Frozen Evaluator, Holdout & Negative Controls:** `plan_sha256`, `oracle_sha256`, `holdout_sha256`, `negative_controls_sha256`, `checks_spec_sha256`, `evaluator_sha256`, and `policy_sha256` are frozen before Maker execution and re-verified before and after evaluation. Maker receives only `maker_view` (never holdout cases or oracle internals).
3. **Matched Isolation & Finite Budget:** Baseline and candidate run in separate, explicitly owned disposable clones under an external `workspace_root`, holding `baseline_revision`, workload, repetitions, and environment constant. Finite `max_wall_seconds`, `max_rounds`, and optional `max_tokens`/`max_cost_usd` are enforced; unavailable token/cost metering is labelled `NOT_VERIFIED` and fails closed when `require_token_budget` or `require_cost_budget` is set.
4. **Hard-Gate Non-Override & Safe Discard:** Any tampering, unauthorized/protected path edit, metric gaming, mandatory check failure/regression, holdout failure/missing, negative-control failure, or budget exhaustion forces `REJECT` (or `ABORTED`). Owned disposable workspaces are safely discarded via ownership-marker verification without touching `source_repo` or `main`.

---

## 2. Recorded Controlled-Fixture Experiment Runs (`CONTROLLED_FIXTURE`)

Reproducible via:

```bash
python3 scripts/agent_harness/improvement.py demo \
  --journal /tmp/p08d-demo/journal.sqlite \
  --evidence-dir /tmp/p08d-demo/evidence \
  --workspace-root /tmp/p08d-demo/workspaces
```

| Experiment ID | Mode | Hypothesis / Scenario | Target Metric & Delta | Holdout & Negative Controls | Decision & Reason Code | Promotion & Recovery |
|---|---|---|---|---|---|---|
| `EXP-DEMO-KEEP-001` | `CONTROLLED_FIXTURE` | Replace noisy lines in `docs/routing_note.md` with focused routing rule (`N=2` reps) | `instruction_snr`: `+0.40` (`>= +0.20`), `0` mandatory regressions | `PASS` / `PASS` | **`KEEP`** (`QUALIFYING_IMPROVEMENT`) | `FIXTURE_ONLY_NOT_PROMOTABLE`; owned disposable workspaces discarded & verified |
| `EXP-DEMO-REJECT-002` | `CONTROLLED_FIXTURE` | Candidate regression in `docs/routing_note.md` (`N=2` reps) | `instruction_snr`: `-0.25` (`< +0.20`) | `PASS` / `PASS` | **`REJECT`** (`INSUFFICIENT_IMPROVEMENT_OR_REGRESSION`) | `NOT_PROMOTED`; owned disposable workspaces discarded & baseline preserved |
| `EXP-DEMO-GAMING-003` | `CONTROLLED_FIXTURE` | Seeded metric-gaming attempt modifying protected `AGENTS.md` (`N=1` rep) | Unauthorized protected edit detected before decision | `PASS` / `FAIL` (`tampering_detected`) | **`REJECT`** (`TAMPERING_OR_METRIC_GAMING`) | `NOT_PROMOTED`; owned disposable workspaces discarded & baseline preserved |

---

## 3. Verified Negative-Control & Integrity Coverage (`test_improvement.py`)

- **Stale, Tampered & Replayed Evidence:** Hash mismatch on `candidate_eval.json`, cross-experiment artifact replay, and forged `KEEP` decision in `decision_record.json` / `Journal` all raise `TamperingError`.
- **Unauthorized Promotion:** Missing `approved_by`, promoting `REJECT`, promoting `CONTROLLED_FIXTURE`, and targeting `main` all raise `UnauthorizedPromotionError`.
- **Budget & Metering:** Exhausted wall/round budget and `require_token_budget=True` with `NOT_VERIFIED` metering deterministically resolve to `REJECT`.
- **Unowned / Symlinked Workspace Protection:** `discard_disposable_workspace` refuses cleanup without an exact matching external ownership marker or if any symlink component is present.
- **Unverified Dimensions (kept `NOT_VERIFIED`):** Live LLM provider evaluation (`REPRESENTATIVE_TASK` multi-model runs), human rubric calibration (`OD-06`/`OD-09`), and P08-E orchestration overhead comparison remain `NOT_VERIFIED` pending separate scoped issues.
