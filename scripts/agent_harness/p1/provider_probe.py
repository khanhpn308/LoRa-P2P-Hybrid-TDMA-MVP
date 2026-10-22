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

from p1.provider_runtime import (IsolatedCLI, RuntimeBlocked, _run, evaluate_probe,
                                 safe_probe_diagnostic, verify_preinstalled_resources)

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
    parser.add_argument("--accept-docker-only-isolation", action="store_true",
                        help="Explicitly accept Codex inner sandbox disabled; Docker remains the only OS boundary")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        config = IsolatedCLI(args.provider, args.image_id, args.network, args.profile_volume)
        if args.accept_docker_only_isolation and (
                args.provider != "codex" or not args.execute
                or not args.confirm_external_egress_policy):
            raise RuntimeBlocked(
                "Docker-only isolation requires Codex execute plus approved egress")
        with tempfile.TemporaryDirectory(prefix="lora-safe-probe-") as folder:
            snapshot = pathlib.Path(folder)
            (snapshot / "README.txt").write_text(
                "Temporary harmless test fixture. No repository content or secrets.\n")
            name = "lora-p1-probe-" + args.provider + "-" + uuid.uuid4().hex[:8]
            command = config.command(
                snapshot, name, PROMPTS[args.provider],
                docker_only_isolation=args.accept_docker_only_isolation)
            if not args.execute:
                # Do not print actual Docker args including credential profile volume.
                print(json.dumps({
                    "status": "PLAN_ONLY",
                    "provider": args.provider,
                    "image_id": args.image_id,
                    "network": args.network,
                    "snapshot": "disposable_read_only",
                    "profile": "dedicated_provider_volume",
                    "sandbox_boundary": "codex_inner_read_only",
                    "model_calls": 0,
                    "requires": "externally reviewed egress and provider authentication",
                }, indent=2))
                return 0
            if not args.confirm_external_egress_policy:
                raise RuntimeBlocked(
                    "Missing operator confirmation of external egress + isolated auth policy")
            verify_preinstalled_resources(config)
            code, stdout, stderr = _run(command, timeout=args.timeout, name=name)
            try:
                receipt = evaluate_probe(args.provider, code, stdout, stderr)
            except RuntimeBlocked as exc:
                # Do not disclose stderr: it can include auth, account, or prompt data.
                print(json.dumps({
                    "status": "BLOCKED",
                    "reason": str(exc)[:200],
                    "sandbox_boundary": (
                        "docker_outer_only" if args.accept_docker_only_isolation
                        else "codex_inner_read_only" if args.provider == "codex"
                        else "provider_default"),
                    "diagnostic": safe_probe_diagnostic(
                        args.provider, code, stdout, stderr),
                }, indent=2))
                return 2
            result = receipt.as_json()
            result["sandbox_boundary"] = (
                "docker_outer_only" if args.accept_docker_only_isolation
                else "codex_inner_read_only" if args.provider == "codex"
                else "provider_default")
            print(json.dumps(result, indent=2))
            return 0
    except (RuntimeBlocked, ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:200]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
