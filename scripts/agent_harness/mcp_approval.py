"""Operator-owned Ed25519 Issue grants for the local Harness MCP boundary.

An approval is not a model prompt, UI hint, environment flag or bearer token.
The signing key and grant directory MUST be root-owned, not accessible for
writing by the MCP/Worker OS account. No native model may invoke this signer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

AUTH_ROOT = Path("/etc/lora-harness")
_ACTIONS = ("prepare", "worker_handoff", "verify_worker", "run_checks",
            "auditor_handoff", "submit_audit")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")


def canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _strict_json(raw: bytes) -> dict:
    if len(raw) > 16000:
        raise ValueError("Approval file size exceeded")
    def unique(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("Duplicate approval key")
            output[key] = value
        return output
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid constant")))
    if not isinstance(value, dict):
        raise ValueError("Approval must be an object")
    return value


def _checked(path: Path, *, owner: int, maxsize: int, is_dir: bool, private: bool = False) -> bytes:
    if path.is_symlink():
        raise ValueError("Approval path symlink")
    info = path.stat(follow_symlinks=False)
    if info.st_uid != owner or info.st_mode & 0o022:
        raise ValueError("Untrusted approval owner/mode")
    if private and (info.st_mode & 0o077):
        raise ValueError("Private key has unsafe permissions")
    if is_dir:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Approval directory expected")
        return b""
    if not stat.S_ISREG(info.st_mode) or info.st_size > maxsize:
        raise ValueError("Untrusted approval file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        fst = os.fstat(file.fileno())
        if (fst.st_dev, fst.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("Approval file changed while opening")
        raw = file.read(maxsize + 1)
    if len(raw) > maxsize:
        raise ValueError("Unbounded approval file")
    return raw


class ApprovalAuthority:
    def __init__(self, root: Path = AUTH_ROOT, *, test_owner: int | None = None):
        self.root = root
        self.owner = 0 if test_owner is None else test_owner

    def _paths(self):
        _checked(self.root, owner=self.owner, maxsize=0, is_dir=True)
        approvals = self.root / "approvals"
        _checked(approvals, owner=self.owner, maxsize=0, is_dir=True)
        return approvals, self.root / "public.pem"

    def verify(self, *, issue: int, base_sha: str, issue_sha256: str,
               scope: list[str], action: str, expected_id: str | None = None) -> dict:
        if (isinstance(issue, bool) or not isinstance(issue, int) or issue < 1
                or not isinstance(base_sha, str) or not _HEX40.fullmatch(base_sha)
                or not isinstance(issue_sha256, str) or not _HEX64.fullmatch(issue_sha256)
                or not isinstance(scope, list) or not scope
                or not all(isinstance(x, str) for x in scope)
                or action not in _ACTIONS):
            raise ValueError("Invalid approval request")
        approvals, public = self._paths()
        pub = _checked(public, owner=self.owner, maxsize=4096, is_dir=False)
        raw = _checked(approvals / ("issue-%d.json" % issue),
                       owner=self.owner, maxsize=16000, is_dir=False)
        envelope = _strict_json(raw)
        if set(envelope) != {"grant", "signature"}:
            raise ValueError("Approval envelope keys mismatch")
        grant, signature = envelope["grant"], envelope["signature"]
        # Ed25519 signatures are 64 bytes = 128 lowercase hex characters.
        if not isinstance(grant, dict) or not isinstance(signature, str):
            raise ValueError("Invalid grant or signature")
        if not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("Invalid approval signature size")
        try:
            verifier = serialization.load_pem_public_key(pub)
            if not isinstance(verifier, Ed25519PublicKey):
                raise ValueError("Wrong approval public key")
            verifier.verify(bytes.fromhex(signature), canonical(grant))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ValueError("Approval signature mismatch") from exc
        if set(grant) != {"version", "grant_id", "issue", "base_sha", "issue_sha256",
                         "scope", "issued_at", "expires_at", "actions"}:
            raise ValueError("Invalid grant contract")
        if (grant["version"] != 1 or grant["issue"] != issue
                or grant["base_sha"] != base_sha or grant["issue_sha256"] != issue_sha256
                or grant["scope"] != scope or grant["actions"] != list(_ACTIONS)
                or not isinstance(grant["grant_id"], str) or not _HEX32.fullmatch(grant["grant_id"])
                or (expected_id is not None and grant["grant_id"] != expected_id)):
            raise ValueError("Approval not issued for this exact Issue/scope/action")
        now = int(time.time())
        if (not isinstance(grant["issued_at"], int) or isinstance(grant["issued_at"], bool)
                or not isinstance(grant["expires_at"], int) or isinstance(grant["expires_at"], bool)
                or grant["issued_at"] > now + 30
                or grant["expires_at"] < now
                or grant["expires_at"] - grant["issued_at"] > 8*3600):
            raise ValueError("Approval expired or malformed")
        return grant


def _atomic_root_file(path: Path, data: bytes, mode: int) -> None:
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    os.fchmod(fd, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="ROOT-ONLY operator signing station, NEVER an MCP tool")
    parser.add_argument("operation", choices=["init", "approve"])
    parser.add_argument("--issue", type=int)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Root operator interactive terminal required (no automation)")
    os.umask(0o077)
    root = AUTH_ROOT
    if args.operation == "init":
        root.mkdir(mode=0o755, exist_ok=True)
        (root / "approvals").mkdir(mode=0o755, exist_ok=True)
        root.chmod(0o755)
        (root / "approvals").chmod(0o755)
        if (root / "private.pem").exists() or (root / "public.pem").exists():
            parser.error("Key already initialized")
        key = Ed25519PrivateKey.generate()
        _atomic_root_file(root / "private.pem", key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()), 0o600)
        _atomic_root_file(root / "public.pem", key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo), 0o644)
        print("Approval authority initialized; never pass private key to AI")
        return 0
    if not args.issue or args.issue < 1 or args.source is None:
        parser.error("Exact Issue number and trusted source checkout required")
    root_real = args.source.resolve(strict=True)
    # Pin current source SHA, actual Issue body hash and strict allowlist.
    harness = root_real / "scripts" / "agent_harness"
    sys.path.insert(0, str(harness))
    from p1.cli import plan_payload
    details = plan_payload(root_real, args.issue, run_id=uuid.uuid4().hex)
    pinned = details["worktree_plan"].base_sha
    issue_sha = details["issue_sha"]
    scope = list(details["scope"])
    print("Issue #%d\nsource: %s\nbody-sha256: %s\nallowed paths:\n%s" %
          (args.issue, pinned, issue_sha, "\n".join(scope)))
    phrase = "APPROVE #%d %s" % (args.issue, issue_sha[:12])
    if input("Type %s to sign: " % phrase).strip() != phrase:
        raise SystemExit("Denied; no approval signed")
    private = _checked(root / "private.pem", owner=0, maxsize=4096,
                       is_dir=False, private=True)
    key = serialization.load_pem_private_key(private, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("Unsupported signing key")
    grant = {
        "version": 1, "grant_id": uuid.uuid4().hex, "issue": args.issue,
        "base_sha": pinned, "issue_sha256": issue_sha, "scope": scope,
        "issued_at": int(time.time()), "expires_at": int(time.time())+8*3600,
        "actions": list(_ACTIONS),
    }
    payload = canonical(grant)
    signature = key.sign(payload).hex()
    approvals, _ = ApprovalAuthority()._paths()
    out = approvals / ("issue-%d.json" % args.issue)
    _atomic_root_file(out, canonical({"grant": grant, "signature": signature}), 0o644)
    print("Signed independent operator approval for Issue #%d (8h)" % args.issue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
