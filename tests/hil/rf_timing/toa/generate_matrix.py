#!/usr/bin/env python3
"""Executable generator for the versioned SX1276 ToA profile matrix.

Targets MVP V1 combinations:
- Payloads: 12, 24, 32, 48 bytes
- SF: 7 and 8
- BW: 125,000 Hz
- CR: 4/5 (CR=1)
- Preamble: 8 symbols
- Header: Explicit
- CRC: ON
- Sync Word: 0x12
- Freq: 920.250 MHz (Channel 0)
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure local package import works
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from sx1276_toa import (
    export_matrix_to_csv,
    export_matrix_to_json,
    generate_profile_matrix,
)


def main() -> int:
    results = generate_profile_matrix(
        payload_sizes=(12, 24, 32, 48),
        spreading_factors=(7, 8),
        bandwidths=(125_000,),
        coding_rate=1,  # 4/5
        preamble_len=8,
        header_explicit=True,
        crc_on=True,
        sync_word=0x12,
        freq_hz=920_250_000,
    )

    json_path = CURRENT_DIR / "matrix_profile_v1.json"
    csv_path = CURRENT_DIR / "matrix_profile_v1.csv"

    json_text = export_matrix_to_json(results)
    csv_text = export_matrix_to_csv(results)

    json_path.write_text(json_text, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8")

    print(f"Generated {len(results)} profile combinations:")
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")
    for r in results:
        print(f"  SF{r.sf} BW{r.bw_hz/1000:.0f}k PL={r.payload_bytes:2d}B -> ToA = {r.toa_calculated_ms:.3f} ms ({r.toa_calculated_us:.0f} us)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
