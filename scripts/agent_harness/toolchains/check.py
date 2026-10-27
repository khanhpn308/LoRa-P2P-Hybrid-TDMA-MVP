"""Check configured ESP-IDF without invoking AI agents, building, or flashing."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from resolver import MODES, ToolchainError, resolve, normalize_version, load_project_version


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP-IDF portable Host toolchain preflight")
    parser.add_argument("--version", help="Optional assertion against firmware/esp-idf-version.txt")
    parser.add_argument("--mode", default="container_first", choices=sorted(MODES))
    parser.add_argument("--allow-native-fallback", action="store_true")
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[3]
    try:
        baseline = load_project_version(root)
        if args.version is not None and normalize_version(args.version) != baseline:
            raise ToolchainError("Version argument conflicts with project baseline")
        idf = resolve(root, version=baseline, mode=args.mode,
                      allow_native_fallback=args.allow_native_fallback)
    except (ToolchainError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "TOOLCHAIN_VERIFIED_ONLY",
                      "toolchain": idf.evidence()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
