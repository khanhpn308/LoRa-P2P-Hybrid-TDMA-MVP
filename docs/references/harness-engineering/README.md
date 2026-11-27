# Harness Engineering Reference Library

> **Issue:** [#415](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/415) (`[Harness V2][P00-B]`) · **Dependency baseline:** [#413](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/413) (`v0.2.0`, PR #414)
> **Companion index:** [REFERENCE_INDEX.md](REFERENCE_INDEX.md)
> **Normative SPEC:** [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) · **Master Plan:** [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md)

This directory provides versioned, traceable metadata and selective-lookup indexing for the primary coursebook used during Harness V2.0 migration (`P00–P10`). It does **not** store a committed copy of the binary PDF and does **not** create a runtime dependency on PDF parsing tools.

---

## 1. Authority Hierarchy & Conflict Rule

Per [AGENTS.md](../../../AGENTS.md) and [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 and §3.1:

| Artifact | Role | Authority Level |
|---|---|---|
| [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) (`v0.2.0`) | Normative design requirements (`H2-*`, `OD-01..10`) | **Normative design baseline** (`OWNER_APPROVED_DESIGN_BASELINE`); does not override active repository policy before phase authorization |
| [HARNESS_MASTER_PLAN.md](../../harness/HARNESS_MASTER_PLAN.md) (`v0.2.0`) | Phase roadmap (`P00–P10`), ownership, exit gates | **Sequencing & execution governance** within approved Issue scope |
| `learn-harness-engineering-en.pdf` | Background curriculum, patterns, templates, case studies | **Informative reference only** (non-normative; not an official OpenAI/Anthropic specification) |
| [REFERENCE_INDEX.md](REFERENCE_INDEX.md) | Page-verified lookup map (45/45 `H2-*` IDs, 11/11 phases `P00–P10`) | **Informative navigation aid**; cannot alter SPEC clauses or add requirements |

- **Non-transferability of course examples:** Examples in the PDF targeting web apps, OAuth 2.0, SQLAlchemy, `npm`/`pytest`, Playwright click loops, or generic domain layer stacks (`Types → Config → Repo → Service → Runtime → UI`) do **not** apply to ESP32/SX1276 firmware, Go Backend, MQTT/PostgreSQL contracts, or Web/Android clients unless explicitly adapted in the approved SPEC or a separate approved ADR/contract.
- **Conflict rule (`STOP_AND_REPORT`):** If any guidance, template, or metric in the PDF conflicts with `HARNESS_SPEC.md`, `HARNESS_MASTER_PLAN.md`, approved ADRs, versioned `contracts/`, or active `AGENTS.md` policy, the Agent MUST **`STOP_AND_REPORT`**, cite both sources and exact revisions, and escalate to the Owner.
- **No duplicated normative rules:** Detailed normative acceptance obligations stay exclusively in [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md).

---

## 2. Selective Context Loading & Missing-Source Policy

- **Selective loading (mandatory for Harness V2 tasks):** Agents working on Harness V2 design, migration (`P01–P10`), or audit MUST consult [REFERENCE_INDEX.md](REFERENCE_INDEX.md) first and load **only the task-relevant sections and physical page ranges** for the active phase or `H2-*` IDs. Do **not** load all 221 PDF pages into context by default.
- **Product execution unaffected:** Missing local access to `learn-harness-engineering-en.pdf` does **not** block ordinary product engineering tasks (ESP-IDF firmware, Go backend, Web/Android, infrastructure, or product contracts).
- **Source-dependent Harness migration/audit:** When a `P01–P10` task or independent audit depends on verifying exact primary coursebook content or resolving a source citation, missing access to an integrity-verified copy of the source material MUST be reported as `NOT_VERIFIED` or `BLOCKED` (never fabricated from memory).

---

## 3. Verified Source Provenance & Integrity

All metadata below was verified directly against the Owner-supplied PDF bytes, `pdfinfo`, `pdftotext`, and the upstream repository snapshot used to generate it:

| Field | Verified Value |
|---|---|
| **Document title** | `Learn Harness Engineering` (`English coursebook PDF · generated 2026-11-27`) |
| **Canonical filename** | `learn-harness-engineering-en.pdf` |
| **Upstream repository** | `https://github.com/walkinglabs/learn-harness-engineering` (WalkingLab) |
| **Upstream commit / revision** | `fe2c4ebd2010aa877b504e141437729296c934e8` (`2026-11-24 15:42:45 +0800`, Merge PR #77) |
| **PDF generation pipeline** | Upstream VitePress build + `scripts/build-course-pdfs.ts` (`npm run pdf:build`, Playwright Chromium + `pdf-lib` v1.17.1) |
| **PDF metadata** | PDF 1.7 · A4 (`595.92 × 842.88 pts`) · Unencrypted · `CreationDate: 2026-11-27T13:42:55+07:00` |
| **Actual physical page count** | `221` pages (pp. `1–3` Cover & TOC; pp. `4–221` across 55 VitePress sections) |
| **Exact file size** | `7,797,038` bytes (~`7.44 MiB`) |
| **Exact SHA-256** | `777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67` |
| **Source accessibility** | Owner-supplied PDF available in execution environment; upstream Markdown sources accessible at `https://github.com/walkinglabs/learn-harness-engineering` (commit `fe2c4ebd2010aa877b504e141437729296c934e8`) |

---

## 4. License, Redistribution Scope & Why the PDF Binary Is Not Committed

### 4.1 Observed License Evidence & Uncertainties

- **Upstream repository license:** The upstream repository root `LICENSE` is the **MIT License** (`Copyright (c) 2025 WalkingLab`), and `package.json` declares `"license": "MIT"` with `"description": "Course docs for Learn Harness Engineering powered by VitePress."`.
- **Recorded uncertainties (do not assume code license covers generated PDF):**
  1. `learn-harness-engineering-en.pdf` is a locally rendered VitePress/Playwright/`pdf-lib` build output (`artifacts/` is listed in upstream `.gitignore` and is not published as an upstream release asset).
  2. Although the MIT License covers the upstream "software and associated documentation files," the rendered PDF also summarizes/cites third-party articles and workflows (OpenAI, Anthropic, Addy Osmani, LangChain, Thoughtworks/Martin Fowler, Andrej Karpathy, etc.) and embeds browser-rendered glyphs/diagrams (upstream also carries SIL Open Font License notices under `assets/readme/licenses/` and a helper script `get_anthropic_logo.js`). Because standalone binary PDF redistribution rights across all embedded/referenced third-party elements cannot be conclusively established solely from a repository code license, binary redistribution in this repository is withheld.

### 4.2 Repository Size & Policy Checks

Even independently of the license uncertainty above, committing the `7,797,038`-byte (`~7.44 MiB`) binary PDF conflicts with repository size and artifact hygiene rules:

1. **Large-binary Git policy:** [monorepo-guide.md](../../development/monorepo-guide.md) (§ Artifacts policy) directs large binary artifacts not to be pushed into Git (`không đẩy vào Git`), storing traceable links and SHA-256 checksums instead.
2. **Repository precedent (Issue #151):** Commit `b351c40` removed previously tracked training/datasheet PDFs (`1.14–5.26 MB`) from `docs/Books/` to keep the repository lean and avoid unverified corpus bloat.
3. **Target architecture alignment:** [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §5.2 designates `docs/references/` for versioned metadata and links to original material rather than bulky binary copies.
4. **Harness tooling limits:** Host verification scripts ([run.py](../../../scripts/agent_harness/run.py), [snapshot.py](../../../scripts/agent_harness/snapshot.py), [p1/verify.py](../../../scripts/agent_harness/p1/verify.py)) reject binary/oversized diffs (`MAX_FILE_BYTES = 120,000` in `p1/verify.py`), and [quality_gates.py](../../../scripts/agent_harness/quality_gates.py) enforces an `8,000,000`-byte per-file read limit (`7,797,038` bytes leaves minimal margin and increases diff/audit overhead).

**Disposition:** `learn-harness-engineering-en.pdf` is **not committed** to Git. Use the two Markdown files in this directory together with the authorized retrieval paths below.

---

## 5. Authorized Retrieval & Integrity Verification

Do not commit downloaded PDFs or publish private workstation paths/credentials. Retrieve and verify the source using either authorized path:

### Option A — Owner-Supplied Coursebook PDF (exact hash match)

Obtain `learn-harness-engineering-en.pdf` through Owner-authorized project channels outside Git, then verify integrity before citing:

```bash
sha256sum learn-harness-engineering-en.pdf
# Expected: 777e654c404c167020e29d0b0b4519e22c0c72bbcca383d83d873536cd012b67

wc -c learn-harness-engineering-en.pdf
# Expected: 7797038

pdfinfo learn-harness-engineering-en.pdf | grep -E 'Pages|Page size|PDF version'
# Expected: Pages: 221 | Page size: 595.92 x 842.88 pts (A4) | PDF version: 1.7
```

### Option B — Upstream Source Checkout (pinned commit)

Clone the upstream repository at the exact pinned commit to inspect the English Markdown sources (`docs/en/`) or regenerate the coursebook locally:

```bash
git clone https://github.com/walkinglabs/learn-harness-engineering.git
cd learn-harness-engineering
git checkout fe2c4ebd2010aa877b504e141437729296c934e8
```

- **Direct Markdown inspection:** Inspect `docs/en/` (lectures, projects, templates, references, OpenAI Advanced Pack, SOPs) mapped by route path in [REFERENCE_INDEX.md](REFERENCE_INDEX.md).
- **Local PDF regeneration (optional):** Running `npm install && npm run pdf:build` invokes `scripts/build-course-pdfs.ts`. Because `renderCoverPage()` stamps the current UTC date (`generated YYYY-MM-DD`) and Chromium/font versions vary by host, a locally rebuilt PDF may differ in binary SHA-256; verify section alignment against the 55-section structure in [REFERENCE_INDEX.md](REFERENCE_INDEX.md) rather than assuming identical binary bytes across rebuild environments.

---

## 6. Page Numbering Convention (Physical vs. Printed Labels)

`learn-harness-engineering-en.pdf` has **two distinct numbering systems**:

1. **Physical PDF page numbers (`1–221`, 1-based):** Sequential page index across the entire 221-page PDF file (`1–3` cover/TOC, `4–221` body sections). **All page numbers in [HARNESS_SPEC.md](../../harness/HARNESS_SPEC.md) §2 and §4 use physical PDF pages.**
2. **Printed footer labels (`1/N … N/N`):** `scripts/build-course-pdfs.ts` renders each of the 55 VitePress routes as a separate temporary PDF with a centered `pageNumber/totalPages` footer before merging them. Consequently:
   - Physical pages `1–3` (Cover & `Included sections`) have **no printed footer label**.
   - Physical pages `4–221` **restart printed labels at `1/N` at the start of every section** (e.g., physical p. `29` has printed footer `4/7` inside Lecture 04; physical p. `171` has printed footer `6/8` inside Template Guide).

[REFERENCE_INDEX.md](REFERENCE_INDEX.md) records **both** physical PDF page numbers and section-relative printed labels for unambiguous verification.
