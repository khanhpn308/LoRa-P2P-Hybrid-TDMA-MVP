#!/usr/bin/env python3
"""Check that governance/contract scaffold paths exist (NOT radio or product validation)."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    ".github/CODEOWNERS",
    ".github/copilot-instructions.md",
    "docs/architecture/system-overview.md",
    "docs/requirements/requirements.md",
    "docs/verification/acceptance-gates.md",
    "contracts/radio-mac/specification.md",
    "contracts/mqtt/topics.md",
    "contracts/api/openapi.yaml",
    "firmware/gateway_master/CMakeLists.txt",
    "firmware/sensor_node/CMakeLists.txt",
    "backend-go/go.mod",
    "deploy/compose.yaml",
]
missing = [p for p in required if not (root / p).is_file()]
for path in required:
    print(f"{'MISSING' if path in missing else 'OK'} {path}")
if missing:
    raise SystemExit(1)
print("PASS: repository scaffold structure (not feature verification)")
