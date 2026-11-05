"""JSON/JSONL schema definitions and validator for RF timing log streams.

Conforms to Issue #11 data integrity policy:
- Strict evidence classification: CALCULATED_TOA, HOST_SYNTHETIC, SOFTWARE_TIMESTAMP,
  HARDWARE_CAPTURE, EXTERNAL_RF_MEASURED.
- Zero tolerance for missing provenance or invalid timebase references.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping

EVIDENCE_CLASSES = {
    "CALCULATED_TOA",
    "HOST_SYNTHETIC",
    "SOFTWARE_TIMESTAMP",
    "HARDWARE_CAPTURE",
    "EXTERNAL_RF_MEASURED",
}

EVENT_TYPES = {
    "INIT",
    "TX_CMD",
    "TX_START",
    "DIO0_IRQ",
    "TX_DONE",
    "RX_CMD",
    "RX_DONE",
    "RX_TIMEOUT",
    "CAD_DONE",
    "CLOCK_SYNC",
    "OVERFLOW",
    "ERROR",
}

ROLES = {"NODE", "GATEWAY"}


class SchemaValidationError(ValueError):
    """Raised when a log line or JSON object violates timing schema rules."""


@dataclass(frozen=True)
class LogRecord:
    ver: str
    seq: int
    role: str
    dev_id: str
    evt: str
    ts_us: int
    evidence_class: str
    pl_len: int = 0
    ch: int = 0
    status: int = 0
    extra: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_log_record(data: Mapping[str, Any]) -> LogRecord:
    """Validate raw parsed dictionary against schema constraints."""
    if not isinstance(data, (dict, Mapping)):
        raise SchemaValidationError(f"Expected dict mapping, got {type(data).__name__}")

    ver = data.get("ver")
    if ver != "1.0.0":
        raise SchemaValidationError(f"Unsupported schema version: {ver!r} (expected '1.0.0')")

    seq = data.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise SchemaValidationError(f"Invalid sequence number: {seq!r}")

    role = data.get("role")
    if role not in ROLES:
        raise SchemaValidationError(f"Invalid device role: {role!r} (expected one of {sorted(ROLES)})")

    dev_id = data.get("dev_id")
    if not isinstance(dev_id, str) or not dev_id.strip():
        raise SchemaValidationError(f"Invalid or empty dev_id: {dev_id!r}")

    evt = data.get("evt")
    if evt not in EVENT_TYPES:
        raise SchemaValidationError(f"Invalid event type: {evt!r} (expected one of {sorted(EVENT_TYPES)})")

    ts_us = data.get("ts_us")
    if not isinstance(ts_us, int) or isinstance(ts_us, bool) or ts_us < 0:
        raise SchemaValidationError(f"Invalid microsecond timestamp: {ts_us!r}")

    evidence_class = data.get("class") or data.get("evidence_class")
    if evidence_class not in EVIDENCE_CLASSES:
        raise SchemaValidationError(
            f"Invalid or missing evidence class: {evidence_class!r} (expected one of {sorted(EVIDENCE_CLASSES)})"
        )

    pl_len = data.get("pl_len", 0)
    if not isinstance(pl_len, int) or isinstance(pl_len, bool) or pl_len < 0 or pl_len > 255:
        raise SchemaValidationError(f"Invalid payload length: {pl_len!r} (range 0..255)")

    ch = data.get("ch", 0)
    if not isinstance(ch, int) or isinstance(ch, bool) or ch < 0 or ch > 10:
        raise SchemaValidationError(f"Invalid VN920 channel index: {ch!r} (range 0..10)")

    status = data.get("status", 0)
    if not isinstance(status, int) or isinstance(status, bool) or status < 0:
        raise SchemaValidationError(f"Invalid status code: {status!r}")

    extra = data.get("extra", 0)
    if not isinstance(extra, int) or isinstance(extra, bool):
        raise SchemaValidationError(f"Invalid extra field: {extra!r}")

    return LogRecord(
        ver=ver,
        seq=seq,
        role=role,
        dev_id=dev_id,
        evt=evt,
        ts_us=ts_us,
        evidence_class=evidence_class,
        pl_len=pl_len,
        ch=ch,
        status=status,
        extra=extra,
    )


def export_json_schema() -> str:
    """Generate standard JSON Schema for the timing record."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ESP32_SX1276_TimingEventRecord",
        "type": "object",
        "required": ["ver", "seq", "role", "dev_id", "evt", "ts_us", "class"],
        "properties": {
            "ver": {"type": "string", "enum": ["1.0.0"]},
            "seq": {"type": "integer", "minimum": 0},
            "role": {"type": "string", "enum": sorted(ROLES)},
            "dev_id": {"type": "string", "minLength": 1},
            "evt": {"type": "string", "enum": sorted(EVENT_TYPES)},
            "ts_us": {"type": "integer", "minimum": 0},
            "class": {"type": "string", "enum": sorted(EVIDENCE_CLASSES)},
            "pl_len": {"type": "integer", "minimum": 0, "maximum": 255},
            "ch": {"type": "integer", "minimum": 0, "maximum": 10},
            "status": {"type": "integer", "minimum": 0},
            "extra": {"type": "integer"},
        },
        "additionalProperties": True,
    }
    return json.dumps(schema, indent=2)
