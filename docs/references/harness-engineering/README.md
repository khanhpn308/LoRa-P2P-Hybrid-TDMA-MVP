# Harness Engineering Reference Library

> **Issue:** [#415](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/415) (`[Harness V2][P00-B]`) · **Reconciliation:** [#417](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/417) (`[Harness V2][P00-C]`) · **Dependency baseline:** [#413](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/413) (`v0.2.0`, PR #414)
> **Companion index:** [REFERENCE_INDEX.md](REFERENCE_INDEX.md)
> **Normative SPEC:** [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) · **Master Plan:** [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md)

This directory provides versioned, traceable metadata and selective-lookup indexing for the primary coursebook used during Harness V2.0 migration (`P00–P10`). It creates **no runtime dependency** on PDF parsing tools, and ordinary product execution must not require the PDF.

**Current repository state vs. authorization:** The binary coursebook [learn-harness-engineering-en.pdf](learn-harness-engineering-en.pdf) is **currently tracked in Git** (added directly on `main` at commit `a4929e38338e08a451db0c408c832514ff83f94b`). However, its retention and public redistribution remain **`BLOCKED`** pending resolution of third-party/font licensing uncertainties and explicit Owner policy authorization (or separately authorized removal); see §4.

---

## 1. Authority Hierarchy & Conflict Rule

Per [AGENTS.md](../../../AGENTS.md) and [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 and §3.1:

| Artifact | Role | Authority Level |
|---|---|---|
| [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) (`v0.2.0`) | Normative design requirements (`H2-*`, `OD-01..10`) | **Normative design baseline** (`OWNER_APPROVED_DESIGN_BASELINE`); does not override active repository policy before phase authorization |
| [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md) (`v0.2.0`) | Phase roadmap (`P00–P10`), ownership, exit gates | **Sequencing & execution governance** within approved Issue scope |
| [learn-harness-engineering-en.pdf](learn-harness-engineering-en.pdf) | Background curriculum, patterns, templates, case studies | **Informative reference only** (non-normative; not an official OpenAI/Anthropic specification; retention currently `BLOCKED` per §4) |
| [REFERENCE_INDEX.md](REFERENCE_INDEX.md) | Page-verified lookup map (45/45 `H2-*` IDs, 11/11 phases `P00–P10`) | **Informative navigation aid**; cannot alter SPEC clauses or add requirements |

- **Non-transferability of course examples:** Examples in the PDF targeting web apps, OAuth 2.0, SQLAlchemy, `npm`/`pytest`, Playwright click loops, or generic domain layer stacks (`Types → Config → Repo → Service → Runtime → UI`) do **not** apply to ESP32/SX1276 firmware, Go Backend, MQTT/PostgreSQL contracts, or Web/Android clients unless explicitly adapted in the approved SPEC or a separate approved ADR/contract.
- **Conflict rule (`STOP_AND_REPORT`):** If any guidance, template, or metric in the PDF conflicts with `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md`, approved ADRs, versioned `contracts/`, or active `AGENTS.md` policy, the Agent MUST **`STOP_AND_REPORT`**, cite both sources and exact revisions, and escalate to the Owner.
- **No duplicated normative rules:** Detailed normative acceptance obligations stay exclusively in [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md).

---

## 2. Selective Context Loading & Missing-Source Policy

- **Selective loading (mandatory for Harness V2 tasks):** Agents working on Harness V2 design, migration (`P01–P10`), or audit MUST consult [REFERENCE_INDEX.md](REFERENCE_INDEX.md) first and load **only the task-relevant sections and physical page ranges** for the active phase or `H2-*` IDs. Do **not** load all 221 PDF pages or perform bulk PDF extraction into context.
- **Product execution unaffected:** Ordinary product engineering tasks (ESP-IDF firmware, Go backend, Web/Android, infrastructure, or product contracts) do **not** require `learn-harness-engineering-en.pdf`, even if the PDF is removed or marked `BLOCKED`.
- **Source-dependent Harness migration/audit:** When a `P01–P10` task or independent audit depends on verifying exact primary coursebook content or resolving a source citation, verify byte integrity first (§5 Option A) or inspect the pinned upstream Markdown sources (§5 Option B). If an integrity-verified source is inaccessible or unverified, report `NOT_VERIFIED` or `BLOCKED` (never fabricate from memory or silently rebase citations).

---

## 3. Verified Source Provenance & Integrity

All metadata below was verified directly against the tracked PDF bytes (`docs/references/harness-engineering/learn-harness-engineering-en.pdf`), `sha256sum`, `wc -c`, `pdfinfo`, `pdffonts`, `pdfimages`, `pdftotext`, and the pinned upstream repository snapshot at commit `fe2c4ebd2010aa877b504e141437729296c934e8`:

| Field | Verified Value |
|---|---|
| **Document title** | `Learn Harness Engineering` (`English coursebook PDF · generated 2026-11-27`) |
| **Canonical filename & repo path** | [learn-harness-engineering-en.pdf](learn-harness-engineering-en.pdf) (`docs/references/harness-engineering/learn-harness-engineering-en.pdf`) |
| **Tracked commit in this repo** | `a4929e38338e08a451db0c408c832514ff83f94b` (`add pdf`, `2026-11-28 00:29:58 +0700`; direct commit on `main`, see §4.2) |
| **Upstream repository** | `https://github.com/walkinglabs/learn-harness-engineering` (WalkingLab) |
| **Upstream commit / revision** | `fe2c4ebd2010aa877b504e141437729296c934e8` (`2026-11-24T07:42:45Z`, `Merge pull request #77 from TejasQ/add-harness-talk-and-repo`) |
| **PDF generation pipeline** | Upstream VitePress build + `scripts/build-course-pdfs.ts` (`npm run pdf:build`, Playwright Chromium + `pdf-lib` v1.17.1) |
| **PDF metadata** | PDF 1.7 · A4 (`595.92 × 842.88 pts`) · Unencrypted · `CreationDate: 2026-11-27T13:42:55+07:00` · Producer/Creator: `pdf-lib` |
| **Actual physical page count** | `221` pages (pp. `1–3` Cover & TOC; pp. `4–221` across 55 VitePress sections) |
| **Exact file size** | `7,797,038` bytes (~`7.44 MiB`) |
| **Exact SHA-256** | `777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67` |
| **Embedded assets (`pdffonts` / `pdfimages`)** | `9` subsetted font faces (`TimesNewRomanPSMT`, `TimesNewRomanPS-BoldMT`, `Inter-Regular`, `InterVariableItalic`, `JetBrainsMono-Regular`, `Newsreader16pt-Regular`, `DejaVuSans`, `DejaVuSans-Bold`, `DejaVuSansMono`); `0` raster images (`pdfimages -list`); no embedded license/copyright text inside PDF |
| **Source accessibility** | Tracked in Git at `docs/references/harness-engineering/learn-harness-engineering-en.pdf` (**retention/redistribution `BLOCKED`**, §4.3); upstream Markdown sources accessible at `https://github.com/walkinglabs/learn-harness-engineering` (commit `fe2c4ebd2010aa877b504e141437729296c934e8`) |

---

## 4. License, Redistribution Scope, Storage Policy & Current Disposition

### 4.1 Observed License Evidence, Attribution & Remaining Uncertainties

Inspection of `walkinglabs/learn-harness-engineering` at pinned commit `fe2c4ebd2010aa877b504e141437729296c934e8` and the tracked PDF bytes establishes the following facts:

- **Upstream repository license (`LICENSE`, `package.json`):** The upstream root `LICENSE` is the **MIT License** (`Copyright (c) 2025 WalkingLab`), and `package.json` declares `"license": "MIT"` with `"description": "Course docs for Learn Harness Engineering powered by VitePress."`. The MIT License permits copying and distributing "this software and associated documentation files (the 'Software')" **only on condition that**: *"The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software."*
- **Upstream acknowledgments (`README.md`):** Upstream credits [`shareAI-lab/learn-claude-code`](https://github.com/shareAI-lab/learn-claude-code) for course inspiration and ideas, and `docs/en/index.md` / lectures cite external engineering articles (OpenAI, Anthropic, Addy Osmani, LangChain, Thoughtworks/Martin Fowler, Andrej Karpathy, etc.) with inline source references.
- **Upstream build & font notices (`scripts/build-course-pdfs.ts`, `.gitignore`, `assets/readme/licenses/`):**
  1. `learn-harness-engineering-en.pdf` is a generated Playwright/`pdf-lib` export; `artifacts/` is in upstream `.gitignore`, and the compiled PDF is not published as an upstream release asset.
  2. Upstream `assets/readme/licenses/` stores SIL Open Font License notices (`InstrumentSerif-OFL.txt`, `Manrope-OFL.txt`, `NotoSans-OFL.txt`, `NotoSansArabic-OFL.txt`, `NotoSansCJK-OFL.txt`) for `scripts/readme-visuals/` assets—**not** for the fonts embedded in `learn-harness-engineering-en.pdf`.

**Required upstream MIT notice (recorded here for provenance; not present inside the PDF):**

```text
MIT License — Copyright (c) 2025 WalkingLab
Source: https://github.com/walkinglabs/learn-harness-engineering (commit fe2c4ebd2010aa877b504e141437729296c934e8)
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
```

**Remaining redistribution uncertainties (preventing clearance in this `PUBLIC` repository):**

1. **Proprietary embedded font subsets (`TimesNewRomanPSMT`, `TimesNewRomanPS-BoldMT`):** `scripts/build-course-pdfs.ts` sets `font-family: Georgia, "Times New Roman", serif;` for `renderCoverPage()`, and `pdffonts` confirms CID TrueType subsets of `TimesNewRomanPSMT` and `TimesNewRomanPS-BoldMT` are embedded in the cover/TOC (`pp. 1–3`). Times New Roman is a proprietary typeface; WalkingLab's MIT `LICENSE` does not grant or verify redistribution rights for proprietary font subsets embedded in a binary PDF hosted in a public GitHub repository (`khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP`).
2. **Unbundled open-font license notices:** `pdffonts` also shows subsets of `Inter-Regular`, `InterVariableItalic`, `JetBrainsMono-Regular`, `Newsreader16pt-Regular`, `DejaVuSans`, `DejaVuSans-Bold`, and `DejaVuSansMono` (loaded via Google Fonts CSS in `docs/.vitepress/theme/style.css` or system fonts) without corresponding OFL / Bitstream-DejaVu license texts bundled inside the PDF or in this directory.
3. **Missing MIT notice inside the tracked PDF copy:** Neither `pdfinfo` metadata nor the PDF body text (`pdftotext`) carries the required `Copyright (c) 2025 WalkingLab` and MIT permission notice, and no standalone upstream `LICENSE` file is tracked alongside the PDF.
4. **Third-party referenced/adapted materials:** The PDF synthesizes/quotes external industry posts and templates (OpenAI, Anthropic, etc.); third-party copyright or trademark terms on underlying quoted/adapted materials are not independently cleared solely by upstream's MIT code license or Owner preference.

### 4.2 Repository Storage Policy & Harness Gate Conflicts

Retaining the `7,797,038`-byte (`~7.44 MiB`) binary PDF in Git also conflicts with active repository storage rules and approaches tooling limits:

1. **Large-binary Git policy:** [monorepo-guide.md](../../development/monorepo-guide.md) §9 (`Quản lý lưu trữ và dữ liệu`) directs large binary artifacts not to be pushed into Git (`không đẩy vào Git`), storing traceable links and SHA-256 checksums instead.
2. **Repository precedent (Issue #151):** Commit `b351c40` removed previously tracked training/datasheet PDFs (`1.14–5.26 MB`) from `docs/Books/` to keep the repository lean and avoid unverified corpus bloat.
3. **Target architecture alignment:** [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §5.2 designates `docs/references/` for versioned metadata and links to original material (`avoid unauthorized copies`) rather than bulky binary copies.
4. **Harness tooling limits:** Host verification scripts ([run.py](../../../scripts/agent_harness/run.py), [snapshot.py](../../../scripts/agent_harness/snapshot.py), [p1/verify.py](../../../scripts/agent_harness/p1/verify.py), [p1/auto_issue.py](../../../scripts/agent_harness/p1/auto_issue.py)) reject binary/oversized diffs (`MAX_FILE_BYTES = 120,000` in `p1/verify.py`), and [quality_gates.py](../../../scripts/agent_harness/quality_gates.py) enforces `MAX_BYTES = 8_000_000` per file (`7,797,038` bytes leaves only `202,962` bytes / `~2.5%` margin).
5. **Commit provenance note:** Commit `a4929e38338e08a451db0c408c832514ff83f94b` added the PDF directly on `main` without G0 intake or PR review; that historical commit is recorded here as an observed repository fact and is **not** a precedent for bypassing G0 or waiving repository policy.

### 4.3 Current Disposition: `BLOCKED` (Tracked in Git, Pending Remediation or Policy Exception)

- **Actual tracked state:** `docs/references/harness-engineering/learn-harness-engineering-en.pdf` **exists in Git** at `main` (`a4929e38`).
- **Retention & distribution authorization:** **`BLOCKED` (`REDISTRIBUTION_RIGHTS_UNVERIFIED` / `STORAGE_EXCEPTION_NOT_AUTHORIZED`)**. Because third-party/font redistribution rights are not verified (§4.1) and no approved Owner policy exception currently overrides [monorepo-guide.md](../../development/monorepo-guide.md) §9, Issue #151, or [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §5.2, **this repository does NOT certify retention or authorize public distribution of the PDF binary**.
- **Candidate narrow storage exception (UNAPPROVED / PENDING — reference specification only if later authorized):**
  - *Target:* single file `docs/references/harness-engineering/learn-harness-engineering-en.pdf` (`7,797,038` bytes, SHA-256 `777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67`, upstream `fe2c4ebd2010aa877b504e141437729296c934e8`).
  - *Rationale:* deterministic physical-page (`1–221`) verification during Harness V2.0 `P01–P10` migration.
  - *Non-waiver invariant:* does **not** weaken binary/size guards in `quality_gates.py`, `p1/verify.py`, `snapshot.py`, or `run.py`, and does **not** permit any other binaries in Git.
  - *Review / removal condition:* expire and remove at `P10` completion, or earlier if redistribution rights remain unresolved.
- **Escalation & separately authorized remediation options (choose via new scoped Issue):**
  1. **Recommended — Remove binary from public Git:** Remove `docs/references/harness-engineering/learn-harness-engineering-en.pdf` under a separately authorized cleanup Issue/PR (retaining [REFERENCE_INDEX.md](REFERENCE_INDEX.md), SHA-256 verification, and pinned upstream Markdown checkout under §5 Option B / private Owner channel distribution).
  2. **Conditional retention (requires both legal + policy clearance):** Clear all embedded font/third-party redistribution issues (e.g., rebuild without proprietary `Times New Roman` and bundle required MIT + OFL/DejaVu notices—noting any rebuild changes SHA-256 and requires citation re-verification under a separate Issue) **and** pass an explicit Owner policy amendment authorizing the single-file storage exception against `monorepo-guide.md` §9 and `HARNESS_SPEC.md` §5.2.

---

## 5. Source Access, Integrity Verification & Upstream Alternative

### Option A — Tracked Repository PDF (Integrity Check Mandatory; Retention `BLOCKED`)

The binary is currently tracked at [learn-harness-engineering-en.pdf](learn-harness-engineering-en.pdf) (`docs/references/harness-engineering/learn-harness-engineering-en.pdf`), though its retention/redistribution status remains **`BLOCKED`** (§4.3). Before referencing it in any local source-dependent `P01–P10` task or audit, verify exact byte integrity (any mismatch => `STOP_AND_REPORT`; do not silently replace or rebase citations):

```bash
sha256sum docs/references/harness-engineering/learn-harness-engineering-en.pdf
# Expected: 777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67

wc -c docs/references/harness-engineering/learn-harness-engineering-en.pdf
# Expected: 7797038

pdfinfo docs/references/harness-engineering/learn-harness-engineering-en.pdf | grep -E 'Pages|Page size|PDF version'
# Expected: Pages: 221 | Page size: 595.92 x 842.88 pts (A4) | PDF version: 1.7
```

*(If the PDF is later removed per §4.3, obtain the exact-hash artifact only through Owner-authorized private channels outside Git and run the same three checks before use.)*

### Option B — Upstream Source Checkout (Pinned Commit, Non-Binary Alternative)

Clone the upstream repository at the exact pinned commit to inspect the English Markdown sources (`docs/en/`) without relying on the committed binary PDF:

```bash
git clone https://github.com/walkinglabs/learn-harness-engineering.git
cd learn-harness-engineering
git checkout fe2c4ebd2010aa877b504e141437729296c934e8
```

- **Direct Markdown inspection:** Inspect `docs/en/` (lectures, projects, templates, references, OpenAI Advanced Pack, SOPs) mapped by route path in [REFERENCE_INDEX.md](REFERENCE_INDEX.md).
- **PDF vs. Markdown equivalence limitations:**
  1. Physical PDF page numbers (`1–221`) exist only in the merged Playwright/`pdf-lib` PDF artifact and do **not** correspond 1:1 to Markdown line numbers; use the section titles and upstream route paths in [REFERENCE_INDEX.md](REFERENCE_INDEX.md) to locate equivalent `docs/en/` sections.
  2. VitePress/Playwright rendering evaluates custom styles, Mermaid diagrams, and generates Cover/TOC (`pp. 1–3`) dynamically at build time.
  3. **Local PDF regeneration (optional):** Running `npm install && npm run pdf:build` invokes `scripts/build-course-pdfs.ts`. Because `renderCoverPage()` stamps the current UTC date (`generated YYYY-MM-DD`) and host Chromium/font availability varies (including whether `Times New Roman` vs. fallback serif is resolved), a locally rebuilt PDF will differ in SHA-256 and may shift page breaks; verify section alignment against the 55-section structure in [REFERENCE_INDEX.md](REFERENCE_INDEX.md) rather than assuming identical binary bytes across rebuild environments.

---

## 6. Page Numbering Convention (Physical vs. Printed Labels)

`learn-harness-engineering-en.pdf` has **two distinct numbering systems**:

1. **Physical PDF page numbers (`1–221`, 1-based):** Sequential page index across the entire 221-page PDF file (`1–3` cover/TOC, `4–221` body sections). **All page numbers in [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 and §4 use physical PDF pages.**
2. **Printed footer labels (`1/N … N/N`):** `scripts/build-course-pdfs.ts` renders each of the 55 VitePress routes as a separate temporary PDF with a centered `pageNumber/totalPages` footer before merging them. Consequently:
   - Physical pages `1–3` (Cover & `Included sections`) have **no printed footer label**.
   - Physical pages `4–221` **restart printed labels at `1/N` at the start of every section** (e.g., physical p. `29` has printed footer `4/7` inside Lecture 04; physical p. `171` has printed footer `6/8` inside Template Guide).

[REFERENCE_INDEX.md](REFERENCE_INDEX.md) records **both** physical PDF page numbers and section-relative printed labels for unambiguous verification.
