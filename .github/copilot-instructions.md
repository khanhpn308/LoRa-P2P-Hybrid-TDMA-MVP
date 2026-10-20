# Repository-wide AI instructions

You work in a LoRa **P2P** monorepo, NOT LoRaWAN. The Gateway is the **local real-time TDMA Master**; Go schedules offline, but never controls individual TX/RX instants via MQTT. No ChirpStack, OTAA, LoRaWAN PHY/MAC package, or unapproved dependencies.

Before code changes:
1. Link to a GitHub Issue with acceptance criteria; inspect `docs/requirements/` and `contracts/`.
2. Mark all unmeasured constants (`SF/BW/CR`, power, 8-byte MAC header, timeslot widths, guard, <3 s alert target, RF limits) as **TBD/NOT_VERIFIED** unless backed by measurements or signed ADR.
3. Every Issue MUST define `Target Directories (allowed paths)` with explicit repo-root-relative paths. Edit ONLY listed paths. If a new source, test, doc, migration, or contract file is required outside scope, STOP and update the Issue scope with owner approval FIRST. Do not interpret broad workstream names as permission to modify adjacent modules.
3a. For every PR, list intended Target Directories and compare actual changed files to approved Issue scope; contract changes require cross-component technical review.
4. Add tests and update docs with code. Never claim simulation equals measured RF/HIL evidence.
5. Never write secrets/keys/certificates/passwords into source, fixtures, logs or replies.
6. All final approvals, RF compliance conclusions and releases require humans. AI may propose, not self-approve.

Review `.github/instructions/*.instructions.md` for path-specific rules.
