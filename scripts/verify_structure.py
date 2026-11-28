#!/usr/bin/env python3
"""Check monorepo foundation invariants. This does NOT test HIL/RF/security/compliance."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    ".github/CODEOWNERS",
    "AGENTS.md",
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
    ".go-version",
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

if (root / "scripts/agent_harness/advanced_pack.py").is_file():
    for path in (
        "docs/harness/ADVANCED_PACK.md",
        "docs/QUALITY_SCORE.md",
        "docs/generated/db-schema.md",
    ):
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

for name in ("sx1276_driver", "lora_mac", "airtime_policy"):
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

# Pinning check is static; passing it does not prove Go 1.27.3 was installed or tests ran.
expected_go = "1.27.3"
version_file = root / ".go-version"
module_file = root / "backend-go/go.mod"
workflow_file = root / ".github/workflows/ci-backend.yml"
if version_file.is_file():
    pinned = version_file.read_text(encoding="utf-8").strip()
    if pinned != expected_go:
        failures.append(f".go-version must be {expected_go}, got {pinned!r}")
    else:
        print(f"OK .go-version locks {expected_go}")
if module_file.is_file():
    import re

    match = re.search(r"(?m)^go\s+(\S+)\s*$", module_file.read_text(encoding="utf-8"))
    if not match or match.group(1) != expected_go:
        failures.append(f"backend-go/go.mod must declare go {expected_go}")
    else:
        print(f"OK backend-go/go.mod requires Go {expected_go}")
if workflow_file.is_file():
    workflow = workflow_file.read_text(encoding="utf-8")
    for token in (f"go-version: '{expected_go}'", "GOTOOLCHAIN: local",
                  "go env GOVERSION", 'cat ../.go-version'):
        if token not in workflow:
            failures.append(f"ci-backend.yml missing lock check: {token}")
    if not any("ci-backend.yml missing lock check" in f for f in failures):
        print(f"OK CI checks exact Go {expected_go} and local toolchain")

if failures:
    for failure in failures:
        print(f"FAIL: {failure}")
    raise SystemExit(1)
print("PASS: static monorepo foundation checks; not GitHub Project field/HIL or build proof")
