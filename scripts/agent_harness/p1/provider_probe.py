"""Explicit operator-driven, read-only Codex/AGY container smoke test.

Default = PLAN_ONLY. --execute requires network/identity review external to
this tool, confirmed isolated credentials and a disposable dedicated provider image.
This does NOT run a Worker coding task or review a real candidate.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
import uuid

if __package__ in ("", None):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from p1.provider_runtime import IsolatedCLI, RuntimeBlocked, _run, evaluate_probe, verify_preinstalled_resources

PROMPTS = {
    "codex": "Respond with exactly CODEX_SMOKE_OK. Do not use tools or modify files.",
    "agy": "Respond with exactly AGY_SMOKE_OK. Do not use tools or modify files.",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="P1-B2-B isolated live read-only provider probe")
    parser.add_argument("--provider", required=True, choices=["codex", "agy"])
    parser.add_argument("--image-id", required=True, help="Reviewed preinstalled image sha256 ID")
    parser.add_argument("--network", required=True, help="Governed lora-agent-egress-* network")
    parser.add_argument("--profile-volume", required=True, help="Provider-dedicated authentication volume")
    parser.add_argument("--execute", action="store_true", help="Execute provider smoke test, not coding")
    parser.add_argument("--confirm-external-egress-policy", action="store_true",
                        help="Operator confirms egress restriction and isolated auth are externally reviewed")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        config = IsolatedCLI(args.provider, args.image_id, args.network, args.profile_volume)
        with tempfile.TemporaryDirectory(prefix="lora-safe-probe-") as folder:
            snapshot = pathlib.Path(folder)
            (snapshot / "README.txt").write_text(
                "Temporary harmless test fixture. No repository content or secrets.\n")
            name = "lora-p1-probe-" + args.provider + "-" + uuid.uuid4().hex[:8]
            command = config.command(snapshot, name, PROMPTS[args.provider])
            if not args.execute:
                # Do not print actual Docker args including credential profile volume.
                print(json.dumps({
                    "status": "PLAN_ONLY",
                    "provider": args.provider,
                    "image_id": args.image_id,
                    "network": args.network,
                    "snapshot": "disposable_read_only",
                    "profile": "dedicated_provider_volume",
                    "model_calls": 0,
                    "requires": "externally reviewed egress and provider authentication",
                }, indent=2))
                return 0
            if not args.confirm_external_egress_policy:
                raise RuntimeBlocked(
                    "Missing operator confirmation of external egress + isolated auth policy")
            verify_preinstalled_resources(config)
            code, stdout, stderr = _run(command, timeout=args.timeout, name=name)
            receipt = evaluate_probe(args.provider, code, stdout, stderr)
            print(json.dumps(receipt.as_json(), indent=2))
            return 0
    except (RuntimeBlocked, ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:200]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
