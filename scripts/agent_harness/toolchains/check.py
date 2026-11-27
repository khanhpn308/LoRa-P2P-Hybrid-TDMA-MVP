"""Check configured ESP-IDF without invoking AI agents, building, or flashing."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

try:
    from .resolver import MODES, ToolchainError, resolve, normalize_version, load_project_version
except ImportError:
    from resolver import MODES, ToolchainError, resolve, normalize_version, load_project_version

FIRMWARE_TARGETS = ("gateway_master", "sensor_node")


def check_dependency_cache(repo: pathlib.Path) -> dict[str, dict]:
    """Inspect managed_components cache against firmware dependencies.lock."""
    status: dict[str, dict] = {}
    for target in FIRMWARE_TARGETS:
        target_dir = repo / "firmware" / target
        lock = target_dir / "dependencies.lock"
        if not lock.is_file():
            status[target] = {"lockfile": False, "cached": True, "detail": "No dependencies.lock"}
            continue
        managed = target_dir / "managed_components"
        try:
            lock_text = lock.read_text(encoding="utf-8")
        except OSError:
            status[target] = {"lockfile": True, "cached": False, "detail": "Unreadable dependencies.lock"}
            continue
        missing_dirs: list[str] = []
        if not managed.is_dir() or not any(managed.iterdir()):
            missing_dirs.append("managed_components")
        elif "espressif/mqtt" in lock_text and not (managed / "espressif__mqtt").is_dir():
            missing_dirs.append("managed_components/espressif__mqtt")
        status[target] = {
            "lockfile": True,
            "cached": not missing_dirs,
            "missing": missing_dirs,
            "detail": "Cached" if not missing_dirs else "Missing offline dependency cache: " + ", ".join(missing_dirs),
        }
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP-IDF portable Host toolchain preflight")
    parser.add_argument("--version", help="Optional assertion against firmware/esp-idf-version.txt")
    parser.add_argument("--mode", default="container_first", choices=sorted(MODES))
    parser.add_argument("--allow-native-fallback", action="store_true")
    parser.add_argument("--repo", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[3],
                        help="Target repository checkout path")
    parser.add_argument("--check-deps", action="store_true",
                        help="Fail closed (exit 2) if firmware managed_components cache is missing")
    args = parser.parse_args()
    root = args.repo.resolve()
    try:
        baseline = load_project_version(root)
        if args.version is not None and normalize_version(args.version) != baseline:
            raise ToolchainError("Version argument conflicts with project baseline")
        idf = resolve(root, version=baseline, mode=args.mode,
                      allow_native_fallback=args.allow_native_fallback)
        deps = check_dependency_cache(root)
        if args.check_deps:
            missing = [f"{t}: {info['detail']}" for t, info in deps.items() if not info["cached"]]
            if missing:
                raise ToolchainError("; ".join(missing))
    except (ToolchainError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "TOOLCHAIN_VERIFIED_ONLY",
                      "toolchain": idf.evidence(),
                      "dependency_cache": deps}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
