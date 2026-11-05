"""Host collector and manifest generator for ESP32/SX1276 timing log streams.

Processes UART/serial streams or captured JSONL files, validates each entry against
log_schema, tracks sequence continuity, and generates cryptographic run manifests.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, TextIO

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from log_schema import (
    EVIDENCE_CLASSES,
    LogRecord,
    SchemaValidationError,
    validate_log_record,
)


@dataclass
class CollectorSummary:
    total_lines: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    dropped_samples: int = 0
    start_time_us: int | None = None
    end_time_us: int | None = None
    duration_ms: float = 0.0
    evidence_counts: dict[str, int] = field(default_factory=dict)
    event_counts: dict[str, int] = field(default_factory=dict)
    error_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HostCollector:
    """Stream collector and validator for timing records."""

    def __init__(self, allow_synthetic: bool = True) -> None:
        self.allow_synthetic = allow_synthetic
        self.summary = CollectorSummary()
        self.last_seq: int | None = None
        self.records: list[LogRecord] = []

    def process_line(self, line_num: int, line_text: str) -> LogRecord | None:
        """Process a single raw line, returning validated LogRecord or None."""
        raw = line_text.strip()
        if not raw or raw.startswith("#"):
            return None

        self.summary.total_lines += 1

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.summary.invalid_records += 1
            self.summary.error_log.append(f"Line {line_num}: JSON decode error: {exc}")
            return None

        try:
            record = validate_log_record(parsed)
        except SchemaValidationError as exc:
            self.summary.invalid_records += 1
            self.summary.error_log.append(f"Line {line_num}: Validation error: {exc}")
            return None

        # Verify synthetic permissions
        if record.evidence_class == "HOST_SYNTHETIC" and not self.allow_synthetic:
            self.summary.invalid_records += 1
            self.summary.error_log.append(f"Line {line_num}: HOST_SYNTHETIC rejected in production mode")
            return None

        # Sequence gap / drop tracking
        if self.last_seq is not None:
            if record.seq > self.last_seq + 1:
                gap = record.seq - (self.last_seq + 1)
                self.summary.dropped_samples += gap
            elif record.seq <= self.last_seq:
                self.summary.error_log.append(
                    f"Line {line_num}: Non-increasing sequence {record.seq} after {self.last_seq}"
                )
        self.last_seq = record.seq

        # Time range tracking
        if self.summary.start_time_us is None or record.ts_us < self.summary.start_time_us:
            self.summary.start_time_us = record.ts_us
        if self.summary.end_time_us is None or record.ts_us > self.summary.end_time_us:
            self.summary.end_time_us = record.ts_us

        # Count statistics
        self.summary.valid_records += 1
        self.summary.evidence_counts[record.evidence_class] = (
            self.summary.evidence_counts.get(record.evidence_class, 0) + 1
        )
        self.summary.event_counts[record.evt] = self.summary.event_counts.get(record.evt, 0) + 1

        self.records.append(record)
        return record

    def process_stream(self, stream: Iterable[str]) -> CollectorSummary:
        for idx, line in enumerate(stream, start=1):
            self.process_line(idx, line)

        if self.summary.start_time_us is not None and self.summary.end_time_us is not None:
            span_us = max(0, self.summary.end_time_us - self.summary.start_time_us)
            self.summary.duration_ms = round(span_us / 1000.0, 3)

        return self.summary

    def generate_manifest(
        self,
        repo_dir: Path | None = None,
        operator_notes: str = "Standard test collection",
        rf_tx_enabled: bool = False,
        board_rev: str = "PCB-HW-001",
    ) -> dict[str, Any]:
        """Generate verifiable run manifest."""
        head_sha = "UNKNOWN"
        if repo_dir:
            try:
                res = subprocess.run(
                    ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    head_sha = res.stdout.strip()
            except Exception:
                pass

        manifest_core = {
            "schema_version": "1.0.0",
            "git_commit": head_sha,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "board_rev": board_rev,
            "rf_tx_enabled": rf_tx_enabled,
            "total_lines": self.summary.total_lines,
            "valid_records": self.summary.valid_records,
            "invalid_records": self.summary.invalid_records,
            "dropped_samples": self.summary.dropped_samples,
            "duration_ms": self.summary.duration_ms,
            "evidence_classes": sorted(self.summary.evidence_counts.keys()),
            "operator_notes": operator_notes,
        }
        serialized = json.dumps(manifest_core, sort_keys=True)
        manifest_core["manifest_sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return manifest_core


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP32/SX1276 timing log collector and manifest generator")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input JSONL file or '-' for stdin")
    parser.add_argument("--output-manifest", "-m", type=Path, help="Path to write JSON run manifest")
    parser.add_argument("--disallow-synthetic", action="store_true", help="Reject HOST_SYNTHETIC records")
    args = parser.parse_args()

    collector = HostCollector(allow_synthetic=not args.disallow_synthetic)

    if str(args.input) == "-":
        collector.process_stream(sys.stdin)
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            collector.process_stream(f)

    summary = collector.summary
    print(f"Collection complete: {summary.valid_records} valid, {summary.invalid_records} invalid, {summary.dropped_samples} dropped.")

    if args.output_manifest:
        manifest = collector.generate_manifest(repo_dir=Path.cwd())
        args.output_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Manifest written to: {args.output_manifest}")

    return 0 if summary.invalid_records == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
