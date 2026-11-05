# Hardware in the Loop (HIL) & RF Timing Verification

Run on instrumented ESP32/SX1276 boards with test configuration, firmware SHA, UART log, timestamps and RF instrumentation. Hardware runner and bench setup are NOT present yet.

Gate G1: two-device TX/RX RF and measured time-on-air.
Gate G2/G3: 10–15 nodes, slot drift, simultaneous alerts, reset, lost beacon, local duty limits.
Never claim simulator PASS equals HIL PASS.

---

## RF Timing Toolchain (`tests/hil/rf_timing/`)

Developed in **Issue #11** as an independently closable software and theoretical timing toolchain. Bench RF radiation, hardware measurements, and production Guard Time acceptance belong to **Issue #169**.

### Directory Structure & Subsystems
- **`toa/`**: Deterministic Semtech SX1276 LoRa Time-on-Air (ToA) calculator conforming to Datasheet Rev 7, Section 4.1.1.5–4.1.1.7. Generates verified profile matrices (`matrix_profile_v1.json`, `matrix_profile_v1.csv`).
- **`firmware/`**:
  - `common/`: Bounded, ISR-safe ring buffer (`timing_ring_buffer.h`/`.c`), hardware pinout matching PCB HW-001 (SCK=5, MISO=19, MOSI=27, NSS=18, RST=23, DIO0=26), and public driver adapter/mock boundary to Issue #10. RF TX is **disabled by default (fail-closed)**.
  - `node_timing_app/`: Test-only Node timing application capturing state transitions, microsecond timestamps, and DIO0 IRQs.
  - `gateway_timing_app/`: Test-only Gateway timing application capturing periodic beacons, continuous reception, and slotted ACK turnarounds.
- **`host/`**: Host serial log collector (`host_collector.py`), JSON/JSONL schema (`log_schema.py`, `log_schema.json`), manifest generator, and deterministic synthetic fixtures (`fixtures/`).
- **`analysis/`**: Statistical parser (`timing_stats.py`) with percentiles (P50/P90/P95/P99) and strict provenance verification, plus conservative Guard Time and TDMA slot feasibility calculator (`guard_budget_calculator.py`) for 10–15 nodes.

### Quick Start / Reproduction
```bash
# Run complete toolchain test suite:
python3 tests/hil/rf_timing/test_rf_timing_toolchain.py

# Generate or verify ToA profile matrix:
python3 tests/hil/rf_timing/toa/generate_matrix.py

# Run host log collector against synthetic fixtures:
python3 tests/hil/rf_timing/host/host_collector.py \
    --input tests/hil/rf_timing/host/fixtures/synthetic_nominal_run.jsonl \
    --output-manifest /tmp/run_manifest.json
```

### Documentation & Methodology
- Theoretical method, equations, schema, and handoff to #169: [docs/verification/rf-timing-methodology-and-harness.md](../../docs/verification/rf-timing-methodology-and-harness.md)
- Theoretical Timing Budget ADR: [docs/adr/0004-theoretical-timing-guard-budget.md](../../docs/adr/0004-theoretical-timing-guard-budget.md)
