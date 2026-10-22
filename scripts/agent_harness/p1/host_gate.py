"""P1-B Host CLI: evidence inspection and offline, credential-free build plan.

Defaults to print-only; no Docker launch, AI calls, Git pushes or PR creation.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from p1.state import Journal
from p1.verify import verify_candidate, VerificationBlocked
from p1.runtime_boundary import BuildBoundary, BoundaryError
from toolchains.resolver import load_project_version, ToolchainError


def main() -> int:
    p = argparse.ArgumentParser(description="P1-B read-only Host candidate gate")
    p.add_argument("--run-id", required=True)
    p.add_argument("--state", type=pathlib.Path, required=True,
                   help="Explicit Host state DB outside Worker worktree")
    p.add_argument("--image-id", help="Verified local espressif/idf:v6.1 image sha256:...")
    args = p.parse_args()
    try:
        if not args.state.is_file() or args.state.is_symlink():
            raise VerificationBlocked("Host SQLite journal not found or is a symlink")
        with Journal(args.state) as journal:
            receipt = verify_candidate(journal, args.run_id)
            job = journal.get(args.run_id)
        # Owner-approved ESP-IDF 6.1 baseline comes from worktree, not Issue text.
        version = load_project_version(pathlib.Path(job["worktree"]))
        if version != "6.1":
            raise VerificationBlocked("Unexpected ESP-IDF baseline")
        receipt["esp_idf"] = "v" + version
        if args.image_id:
            boundary = BuildBoundary(args.image_id)
            receipt["build_commands"] = [
                boundary.command(pathlib.Path(job["worktree"]), x)
                for x in ("gateway_master", "sensor_node")
            ]
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    except (VerificationBlocked, BoundaryError, ToolchainError, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:250]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
