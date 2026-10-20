#!/usr/bin/env python3
"""Check monorepo foundation invariants. This does NOT test HIL/RF/security/compliance."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    ".github/CODEOWNERS",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    "docs/architecture/system-overview.md",
    "docs/requirements/requirements.md",
    "docs/verification/acceptance-gates.md",
    "docs/development/task-breakdown-readiness.md",
    "contracts/radio-mac/specification.md",
    "contracts/mqtt/topics.md",
    "contracts/api/openapi.yaml",
    "firmware/gateway_master/CMakeLists.txt",
    "firmware/sensor_node/CMakeLists.txt",
    "backend-go/go.mod",
    "deploy/compose.yaml",
    "scripts/setup_project_gate.sh",
]
failures = []
for path in required:
    exists = (root / path).is_file()
    print(f"{'OK' if exists else 'MISSING'} {path}")
    if not exists:
        failures.append(path)

cmake_line = 'set(EXTRA_COMPONENT_DIRS "../components")'
for target in ("gateway_master", "sensor_node"):
    path = f"firmware/{target}/CMakeLists.txt"
    full = root / path
    if full.is_file() and cmake_line not in full.read_text(encoding="utf-8"):
        failures.append(f"{path} lacks shared components directory")
    elif full.is_file():
        print(f"OK {path} registers ../components")

for name in ("sx1276_driver", "lora_mac", "tdma_common", "airtime_policy"):
    full = root / "firmware/components" / name
    if not full.is_dir():
        failures.append(f"missing component directory: {name}")
    elif not (full / "CMakeLists.txt").is_file():
        print(f"NOT_IMPLEMENTED firmware/components/{name}/CMakeLists.txt (follow-up firmware task)")
    else:
        print(f"PRESENT firmware/components/{name}/CMakeLists.txt")

issue_forms = (
    "embedded_task.yml", "backend_task.yml", "frontend_task.yml",
    "research_task.yml", "bug_report.yml",
)
for form in issue_forms:
    path = root / ".github/ISSUE_TEMPLATE" / form
    if not path.is_file():
        failures.append(f"missing Issue form: {form}")
    elif "id: target_directories" not in path.read_text(encoding="utf-8"):
        failures.append(f"missing Target Directories in {form}")
    else:
        print(f"OK {form} includes mandatory Target Directories input")

if failures:
    for failure in failures:
        print(f"FAIL: {failure}")
    raise SystemExit(1)
print("PASS: static monorepo foundation checks; not GitHub Project field/HIL or build proof")
