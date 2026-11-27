# Harness Engineering Reference Library

> **Issue:** [#419](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/419) (`[Harness V2][P00-D]`) · **Prior baseline:** [#413](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/413) (`v0.2.0`, PR #414), [#415](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/415) (`P00-B`, PR #416), [#417](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/417) (`P00-C`, PR #418)
> **Local index & coverage ledger:** [REFERENCE_INDEX.md](REFERENCE_INDEX.md)
> **Local knowledge corpus:** [knowledge/01-foundations-and-instructions.md](knowledge/01-foundations-and-instructions.md) … [knowledge/06-templates-advanced-pack-and-sops.md](knowledge/06-templates-advanced-pack-and-sops.md)
> **Normative SPEC:** [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) · **Master Plan:** [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md)

This directory contains the self-contained, repository-local Markdown knowledge extracted from the pinned English sources (`docs/en/`) of **Learn Harness Engineering** (`fe2c4ebd2010aa877b504e141437729296c934e8`), plus a complete requirement/phase/section routing index ([REFERENCE_INDEX.md](REFERENCE_INDEX.md)). All `P01–P10` Harness V2 execution and audit tasks operate **offline using local repository files only**—without retrieving any PDF, upstream GitHub repository, external website, or separate clone for course-derived guidance.

---

## 1. Authority Hierarchy & Non-Transferability

Per [AGENTS.md](../../../AGENTS.md) and [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 and §3.1:

| Artifact | Role | Authority Level |
|---|---|---|
| [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) (`v0.2.0`) | Normative design requirements (`H2-*`, `OD-01..10`) | **Normative design baseline** (`OWNER_APPROVED_DESIGN_BASELINE`); does not override active repository policy before phase authorization |
| [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md) (`v0.2.0`) | Phase roadmap (`P00–P10`), ownership, exit gates | **Sequencing & execution governance** within approved Issue scope |
| [REFERENCE_INDEX.md](REFERENCE_INDEX.md) | Routing & coverage ledger (`45/45` `H2-*`, `11/11` phases, `55/55` sections) | **Informative navigation aid**; cannot alter SPEC clauses or add requirements |
| [knowledge/01..06.md](knowledge/01-foundations-and-instructions.md) | Self-contained extracted definitions, procedures, templates, SOPs | **Informative reference only** (non-normative; not an official OpenAI/Anthropic standard) |

- **Non-transferability of course examples:** Course examples targeting Electron desktop apps, OAuth 2.0, FastAPI/SQLAlchemy, `npm`/`pytest`, Playwright/Chrome DevTools click loops, or generic domain layer stacks (`Types -> Config -> Repo -> Service -> Runtime -> UI`) do **not** apply to ESP32/SX1276 firmware, Go Modular Monolith, MQTT/PostgreSQL contracts, or Web/Android clients unless explicitly adapted in `HARNESS_SPEC.md` or a separate approved ADR/contract.
- **Examples as data only:** Never execute, vendor, or activate upstream TypeScript, Python, shell, or skill code (`skills/harness-creator/`, `tools/audit-harness.sh`) from course examples.
- **Conflict rule (`STOP_AND_REPORT`):** If any guidance, template, or metric in `knowledge/` conflicts with `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md`, approved ADRs, versioned `contracts/`, or active `AGENTS.md` policy, the Agent MUST **`STOP_AND_REPORT`**, cite both sources and exact revisions, and escalate to the Owner.
- **No duplicated normative rules:** Detailed normative obligations stay exclusively in [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md).

---

## 2. Local-First Selective Context Policy

- **Mandatory lookup flow for Harness V2 tasks (`P01–P10`, including `P01-A`):**
  1. Identify the active **task** -> **requirement (`H2-*`) or phase (`P00–P10`)**.
  2. Open [REFERENCE_INDEX.md](REFERENCE_INDEX.md) to locate the exact local anchor(s).
  3. Read **only the relevant headings** inside the targeted `knowledge/01..06.md` file(s).
  4. Execute within approved repo authority (`AGENTS.md`, `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md`, ADRs, `contracts/`).
- **Do NOT load all six knowledge files by default:** Bulk-loading all six files into context violates selective context discipline (`H2-INS-04`).
- **Offline sufficiency & course-reference independence:** No remote URL, external clone, PDF reader, PDF build, PDF checksum, or network access is required for course-derived guidance. If a required local concept is missing or appears only as a placeholder/external-only pointer, report `BLOCKED` / `FAIL` rather than fetching externally or fabricating from memory.
- **Ordinary product engineering unaffected:** Standard ESP-IDF firmware, Go backend, Web/Android, or infrastructure Issues do **not** load `docs/references/harness-engineering/knowledge/` unless explicitly scoped; product toolchain/dependency access is separate from course-reference independence.
- **`P01-A` corpus boundary:** P01-A inventory/audit MUST use the internal repository corpus (including local Skills/Standards/Knowledge WP-H and extensibility surfaces) and MUST NOT reintroduce mandatory external coursebook access.

---

## 3. License, Attribution, and Exclusion Record

### 3.1 Upstream MIT License (Retained Verbatim)

The local knowledge files ([knowledge/01-foundations-and-instructions.md](knowledge/01-foundations-and-instructions.md) through [knowledge/06-templates-advanced-pack-and-sops.md](knowledge/06-templates-advanced-pack-and-sops.md)) and [REFERENCE_INDEX.md](REFERENCE_INDEX.md) contain content extracted and adapted from `walkinglabs/learn-harness-engineering` (`docs/en/` at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8`), distributed under the MIT License (`package.json` declares `"license": "MIT"`):

```text
MIT License

Copyright (c) 2025 WalkingLab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Source provenance: `https://github.com/walkinglabs/learn-harness-engineering/tree/fe2c4ebd2010aa877b504e141437729296c934e8` (`2026-11-24T07:42:45Z`). Upstream acknowledges [`shareAI-lab/learn-claude-code`](https://github.com/shareAI-lab/learn-claude-code) for course inspiration.

### 3.2 Scope Verification & Exclusions

1. **Upstream-owned MIT text vs. third-party articles:** Course prose, templates, checklists, SOPs, and lecture structures authored by WalkingLab under `docs/en/` are covered by the MIT License above. External engineering articles cited in lectures and `docs/en/resources/reference/index.md` (OpenAI, Anthropic, LangChain, Addy Osmani, Martin Fowler/Thoughtworks, Cursor, Karpathy, etc.) are **paraphrased/summarized with attribution only**; full third-party passages are not reproduced, and no claim is made that WalkingLab's MIT license transfers third-party copyright or trademark rights.
2. **Excluded non-MIT / render-only / binary assets:**
   - The generated binary PDF (`learn-harness-engineering-en.pdf`) and its embedded proprietary (`TimesNewRomanPSMT`, `TimesNewRomanPS-BoldMT`) and unbundled open font subsets (`Inter`, `JetBrainsMono`, `Newsreader`, `DejaVu`) are **excluded and deleted** from the current tree (§4).
   - Upstream VitePress styles, `assets/readme/`, HTML card markup, and non-English translations (`docs/zh/`, etc.) are **excluded**.
   - Upstream runnable TypeScript/Python/Node/shell teaching projects (`projects/project-01..08/{starter,solution}/src/`, `lectures/*/code/*.ts`, `maker_checker_graph.py`, `skills/harness-creator/`, `tools/audit-harness.sh`) are **not vendored or executed**; harness concepts, schemas, and procedures needed for `P01–P10` are captured as informative Markdown data in `knowledge/01..06.md`.
3. **Gaps & compliance boundary:** Third-party article claims remain informative citations rather than independently verified facts; no claim of blanket legal clearance beyond documented upstream MIT terms and exclusion of non-MIT assets is made.

---

## 4. Current-Tree PDF Removal & Issue #417 Residual Historical Exposure

- **Current-tree disposition:** Under Issue [#419](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/419), `docs/references/harness-engineering/learn-harness-engineering-en.pdf` has been **deleted from the current candidate tree**. There are no mandatory PDF links, PDF parsing steps, PDF build steps, or PDF byte-checksum prerequisites in this library.
- **Historical provenance record (non-operational):** The removed artifact was a `221`-page PDF (`7,797,038` bytes, SHA-256 `777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67`, generated `2026-11-27` via upstream `scripts/build-course-pdfs.ts`), originally added directly on `main` at commit `a4929e38338e08a451db0c408c832514ff83f94b`. Historical page ranges (`pp. 1–221`) in [REFERENCE_INDEX.md](REFERENCE_INDEX.md) and [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) are provenance locators only.
- **Residual historical exposure ([#417](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/417)):**
  - Deleting the PDF from the current tree eliminates ongoing repository checkout bloat, binary-guard collisions (`MAX_BYTES = 8_000_000` in `quality_gates.py`, `MAX_FILE_BYTES = 120_000` in `p1/verify.py`), and ongoing `HEAD` redistribution.
  - **However, current-tree deletion does NOT erase prior Git commit objects (`a4929e38...`), public Git history, existing clones/forks/caches, or resolve historical copyright/font redistribution exposure.**
  - Consistent with repository governance, **no Git history rewrite, force-push, repository visibility change, or automatic closure of Issue #417** is performed under Issue #419.

---

## 5. Future Upstream Updates (Optional, Non-Blocking)

Upstream links remain optional provenance. If future upstream changes in `walkinglabs/learn-harness-engineering` warrant review:
1. Open a dedicated scoped Issue citing the new pinned upstream commit SHA and license status.
2. Inspect diffs read-only outside the candidate tree; check for license/third-party exclusions and conflicts against `HARNESS_SPEC.md`, ADRs, and `AGENTS.md`.
3. Update affected sections in `knowledge/01..06.md` and [REFERENCE_INDEX.md](REFERENCE_INDEX.md) through normal G0 intake, independent audit, and human PR review. Never establish a live network/runtime dependency on upstream.
