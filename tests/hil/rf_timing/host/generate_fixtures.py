#!/usr/bin/env python3
"""Deterministic generator for synthetic test fixtures in tests/hil/rf_timing/host/fixtures/."""

from __future__ import annotations

import json
from pathlib import Path
import random
import sys

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def generate_nominal_fixture(path: Path, cycles: int = 25) -> None:
    """Generate nominal DATA + ACK cycles with realistic microsecond timing."""
    lines: list[str] = []
    seq = 1
    t_us = 10_000_000  # Start at 10.0 s

    # Header / init
    init_rec = {
        "ver": "1.0.0",
        "seq": seq,
        "role": "NODE",
        "dev_id": "NODE_HIL_01",
        "evt": "INIT",
        "ts_us": t_us,
        "class": "HOST_SYNTHETIC",
        "pl_len": 0,
        "ch": 0,
        "status": 0,
        "extra": 0,
    }
    lines.append(json.dumps(init_rec))
    seq += 1

    # Deterministic pseudo-random seed
    rng = random.Random(42)

    for cycle in range(cycles):
        t_us += 100_000  # 100 ms cycle interval

        # TX_CMD
        t_us += rng.randint(5, 15)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_CMD", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 24, "ch": 0, "status": 0, "extra": 7
        }))
        seq += 1

        # TX_START (SPI write dispatch ~25 us)
        t_us += rng.randint(20, 35)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_START", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 24, "ch": 0, "status": 0, "extra": 7
        }))
        seq += 1

        # DIO0_IRQ (Simulated ToA for SF7 PL=24: 61,696 us + jitter)
        t_us += 61_696 + rng.randint(-10, 10)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "DIO0_IRQ", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 24, "ch": 0, "status": 0, "extra": 0
        }))
        seq += 1

        # TX_DONE (Task handles IRQ notify ~15 us)
        t_us += rng.randint(12, 22)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_DONE", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 24, "ch": 0, "status": 0, "extra": 0
        }))
        seq += 1

        # RX_CMD (Turnaround to RxSingle ~60 us)
        t_us += rng.randint(50, 70)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "RX_CMD", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 8, "ch": 0, "status": 0, "extra": 0
        }))
        seq += 1

        # RX_DONE (Slotted ACK arrival ~36 ms)
        t_us += 36_000 + rng.randint(-15, 15)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "RX_DONE", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 8, "ch": 0, "status": 0, "extra": 0
        }))
        seq += 1

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_jitter_burst_fixture(path: Path, cycles: int = 15) -> None:
    """Generate high-jitter burst scenarios simulating FreeRTOS task starvation."""
    lines: list[str] = []
    seq = 1
    t_us = 20_000_000
    rng = random.Random(1337)

    for _ in range(cycles):
        t_us += 50_000

        # TX_CMD with burst scheduling jitter (up to 500 us)
        t_us += rng.randint(50, 500)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_CMD", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 32, "ch": 0, "status": 0, "extra": 7
        }))
        seq += 1

        t_us += rng.randint(100, 400)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_START", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 32, "ch": 0, "status": 0, "extra": 7
        }))
        seq += 1

        # ToA SF7 PL=32: 71,936 us
        t_us += 71_936 + rng.randint(-20, 20)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "DIO0_IRQ", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 32, "ch": 0, "status": 0, "extra": 0
        }))
        seq += 1

        # High task wakeup jitter (up to 800 us)
        t_us += rng.randint(150, 800)
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_DONE", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 32, "ch": 0, "status": 0, "extra": 0
        }))
        seq += 1

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_clock_drift_fixture(path: Path) -> None:
    """Generate multi-interval clock sync drift fixture across 10s, 60s, 300s."""
    lines: list[str] = []
    seq = 1
    # Simulated crystal drift rate: +18.5 PPM (18.5 us per 1 second)
    ppm_drift = 18.5

    windows_s = [10, 60, 300]
    t_gw_us = 100_000_000

    for win_s in windows_s:
        t_gw_us += win_s * 1_000_000
        # Node clock drifted relative to gateway
        accumulated_drift_us = int(win_s * ppm_drift)
        t_node_us = t_gw_us + accumulated_drift_us

        # Gateway Sync Beacon
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "GATEWAY", "dev_id": "GATEWAY_HIL_01",
            "evt": "CLOCK_SYNC", "ts_us": t_gw_us, "class": "HOST_SYNTHETIC",
            "pl_len": 16, "ch": 0, "status": 0, "extra": win_s
        }))
        seq += 1

        # Node latch of beacon
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "CLOCK_SYNC", "ts_us": t_node_us, "class": "HOST_SYNTHETIC",
            "pl_len": 16, "ch": 0, "status": 0, "extra": accumulated_drift_us
        }))
        seq += 1

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_dropped_overflow_fixture(path: Path) -> None:
    """Generate fixture containing buffer overflow events and sequence gaps."""
    lines: list[str] = []
    t_us = 50_000_000

    # Normal sequence 1..5
    for seq in range(1, 6):
        t_us += 1000
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_CMD", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 24, "ch": 0, "status": 0, "extra": 0
        }))

    # OVERFLOW event indicating internal ring buffer drop
    t_us += 500
    lines.append(json.dumps({
        "ver": "1.0.0", "seq": 6, "role": "NODE", "dev_id": "NODE_HIL_01",
        "evt": "OVERFLOW", "ts_us": t_us, "class": "HOST_SYNTHETIC",
        "pl_len": 0, "ch": 0, "status": 1, "extra": 10  # 10 records dropped
    }))

    # Sequence jumps from 6 to 17 (10 dropped samples)
    for seq in range(17, 22):
        t_us += 1000
        lines.append(json.dumps({
            "ver": "1.0.0", "seq": seq, "role": "NODE", "dev_id": "NODE_HIL_01",
            "evt": "TX_DONE", "ts_us": t_us, "class": "HOST_SYNTHETIC",
            "pl_len": 24, "ch": 0, "status": 0, "extra": 0
        }))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_malformed_fixture(path: Path) -> None:
    """Generate negative test cases with malformed lines, invalid values, and unverified claims."""
    lines = [
        '# This is a comment and should be skipped',
        'Not a valid JSON line {{{',
        json.dumps({"ver": "2.0.0", "seq": 1, "role": "NODE", "dev_id": "N1", "evt": "TX_CMD", "ts_us": 100, "class": "HOST_SYNTHETIC"}), # wrong ver
        json.dumps({"ver": "1.0.0", "seq": -5, "role": "NODE", "dev_id": "N1", "evt": "TX_CMD", "ts_us": 100, "class": "HOST_SYNTHETIC"}), # negative seq
        json.dumps({"ver": "1.0.0", "seq": 2, "role": "ALIEN", "dev_id": "N1", "evt": "TX_CMD", "ts_us": 100, "class": "HOST_SYNTHETIC"}), # invalid role
        json.dumps({"ver": "1.0.0", "seq": 3, "role": "NODE", "dev_id": "", "evt": "TX_CMD", "ts_us": 100, "class": "HOST_SYNTHETIC"}), # empty dev_id
        json.dumps({"ver": "1.0.0", "seq": 4, "role": "NODE", "dev_id": "N1", "evt": "INVALID_EVT", "ts_us": 100, "class": "HOST_SYNTHETIC"}), # invalid evt
        json.dumps({"ver": "1.0.0", "seq": 5, "role": "NODE", "dev_id": "N1", "evt": "TX_CMD", "ts_us": -100, "class": "HOST_SYNTHETIC"}), # negative ts
        json.dumps({"ver": "1.0.0", "seq": 6, "role": "NODE", "dev_id": "N1", "evt": "TX_CMD", "ts_us": 100, "class": "FAKE_EVIDENCE"}), # invalid class
        json.dumps({"ver": "1.0.0", "seq": 7, "role": "NODE", "dev_id": "N1", "evt": "TX_CMD", "ts_us": 100, "class": "HOST_SYNTHETIC", "pl_len": 300}), # pl_len > 255
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    generate_nominal_fixture(FIXTURES_DIR / "synthetic_nominal_run.jsonl")
    generate_jitter_burst_fixture(FIXTURES_DIR / "synthetic_jitter_burst.jsonl")
    generate_clock_drift_fixture(FIXTURES_DIR / "synthetic_clock_drift.jsonl")
    generate_dropped_overflow_fixture(FIXTURES_DIR / "synthetic_dropped_overflow.jsonl")
    generate_malformed_fixture(FIXTURES_DIR / "malformed_samples.jsonl")
    print(f"Generated 5 synthetic test fixtures in: {FIXTURES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
