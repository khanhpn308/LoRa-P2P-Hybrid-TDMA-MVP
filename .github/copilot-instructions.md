# Repository-wide AI instructions

You work in a LoRa **P2P** monorepo, NOT LoRaWAN. The Gateway is the **local real-time TDMA Master**; Go schedules offline, but never controls individual TX/RX instants via MQTT. No ChirpStack, OTAA, LoRaWAN PHY/MAC package, or unapproved dependencies.

Before code changes:
1. Link to a GitHub Issue with acceptance criteria; inspect `docs/requirements/` and `contracts/`.
2. Mark all unmeasured constants (`SF/BW/CR`, power, 8-byte MAC header, timeslot widths, guard, <3 s alert target, RF limits) as **TBD/NOT_VERIFIED** unless backed by measurements or signed ADR.
3. Keep change scope within the requested workstream; request explicit review for cross-component contract changes.
4. Add tests and update docs with code. Never claim simulation equals measured RF/HIL evidence.
5. Never write secrets/keys/certificates/passwords into source, fixtures, logs or replies.
6. All final approvals, RF compliance conclusions and releases require humans. AI may propose, not self-approve.

Review `.github/instructions/*.instructions.md` for path-specific rules.
