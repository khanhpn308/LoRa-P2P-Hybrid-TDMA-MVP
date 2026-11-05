#!/usr/bin/env python3
"""Unified test runner for the complete Issue #11 RF Timing Toolchain.

Executes:
1. Python unit & boundary tests for Semtech SX1276 ToA calculator.
2. C host compilation and execution of ring buffer & radio adapter tests.
3. Host collector stream validation against synthetic fixtures.
4. Statistical parser and Guard Time feasibility calculations.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

RF_TIMING_DIR = Path(__file__).resolve().parent
REPO_ROOT = RF_TIMING_DIR.parents[2]


def run_cmd(desc: str, cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[TEST] {desc}...")
    res = subprocess.run(cmd, cwd=str(cwd or REPO_ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {desc}")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        sys.exit(res.returncode)
    print(f"  PASS: {desc}")


def main() -> int:
    print("=== Running Complete RF Timing Toolchain Test Suite ===")

    # 1. ToA Unit & Property Tests
    run_cmd(
        "ToA Calculator Unit Tests",
        [sys.executable, "-m", "pytest", "tests/hil/rf_timing/toa/test_sx1276_toa.py"],
    )

    # 2. C Firmware Host Compile & Run
    common_dir = RF_TIMING_DIR / "firmware" / "common"
    bin_path = Path("/tmp/test_c_ring_buffer_bin")
    compile_cmd = [
        "gcc", "-Wall", "-Wextra", "-Werror", "-std=c11",
        f"-I{common_dir}",
        str(common_dir / "timing_ring_buffer.c"),
        str(common_dir / "radio_adapter_mock.c"),
        str(common_dir / "test_c_ring_buffer.c"),
        "-o", str(bin_path),
    ]
    run_cmd("C Firmware Unit Tests (Compile)", compile_cmd)
    run_cmd("C Firmware Unit Tests (Execute)", [str(bin_path)])
    if bin_path.exists():
        bin_path.unlink()

    # 3. Node & Gateway Host Build Verification
    node_bin = Path("/tmp/node_timing_host_bin")
    node_main = RF_TIMING_DIR / "firmware" / "node_timing_app" / "main"
    run_cmd(
        "Node Timing App (Host Compile)",
        [
            "gcc", "-Wall", "-Wextra", "-Werror", "-std=c11",
            f"-I{common_dir}", f"-I{node_main}",
            str(common_dir / "timing_ring_buffer.c"),
            str(common_dir / "radio_adapter_mock.c"),
            str(node_main / "main.c"),
            "-o", str(node_bin),
        ]
    )
    if node_bin.exists():
        node_bin.unlink()

    gw_bin = Path("/tmp/gw_timing_host_bin")
    gw_main = RF_TIMING_DIR / "firmware" / "gateway_timing_app" / "main"
    run_cmd(
        "Gateway Timing App (Host Compile)",
        [
            "gcc", "-Wall", "-Wextra", "-Werror", "-std=c11",
            f"-I{common_dir}", f"-I{gw_main}",
            str(common_dir / "timing_ring_buffer.c"),
            str(common_dir / "radio_adapter_mock.c"),
            str(gw_main / "main.c"),
            "-o", str(gw_bin),
        ]
    )
    if gw_bin.exists():
        gw_bin.unlink()

    # 4. Analysis and Guard Time Calculator Tests
    run_cmd(
        "Timing Analysis & Guard Calculator Tests",
        [sys.executable, "-m", "pytest", "tests/hil/rf_timing/analysis/test_timing_analysis.py"],
    )

    print("\nALL RF TIMING TOOLCHAIN TESTS PASSED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
