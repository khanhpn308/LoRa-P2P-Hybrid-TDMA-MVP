"""Check configured ESP-IDF without invoking AI agents, building, or flashing."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from resolver import MODES, ToolchainError, resolve


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP-IDF portable Host toolchain preflight")
    parser.add_argument("--version", required=True, help="Engineering-approved ESP-IDF X.Y.Z")
    parser.add_argument("--mode", default="container_first", choices=sorted(MODES))
    parser.add_argument("--allow-native-fallback", action="store_true")
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[3]
    try:
        idf = resolve(root, version=args.version, mode=args.mode,
                      allow_native_fallback=args.allow_native_fallback)
    except (ToolchainError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "TOOLCHAIN_VERIFIED_ONLY",
                      "toolchain": idf.evidence()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
