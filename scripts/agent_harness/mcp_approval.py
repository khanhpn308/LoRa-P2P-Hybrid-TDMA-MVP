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
import subprocess
import stat
import sys
import time
import uuid

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
except ImportError:  # The core Harness unittest runner may not install optional MCP crypto.
    serialization = None
    Ed25519PrivateKey = None
    Ed25519PublicKey = None
    InvalidSignature = None

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
        if Ed25519PublicKey is None or serialization is None:
            raise ValueError("Approval signature verifier dependency unavailable")
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



def _scope_from_body(body: str) -> list[str]:
    """Standalone, fail-closed equivalent of Host scope parsing; no repo code imports."""
    header = re.compile(r"^#{2,6}\s+Target Directories \(allowed paths\)\s*$", re.I)
    item = re.compile(r"^\s*-\s+\x60([^\x60]+)\x60\s*(?:\([^)]*\))?\s*$")
    inside = False
    paths = []
    for line in body.splitlines():
        if not inside:
            if header.match(line):
                inside = True
            continue
        if not line.strip() and not paths:
            continue
        match = item.fullmatch(line)
        if not match:
            if paths:
                break
            raise ValueError("Invalid Issue allowed-path list")
        path = match.group(1)
        if (not path or path.startswith(("/", "./")) or "\\" in path
                or ".." in path.split("/") or "//" in path
                or any(ch in path for ch in "*?[]{}")
                or path.strip() != path):
            raise ValueError("Unsafe Issue allowed path")
        normalized = "/".join(part for part in path.rstrip("/").split("/") if part != ".")
        if not normalized:
            raise ValueError("Root scope forbidden")
        actual = normalized + ("/" if path.endswith("/") else "")
        if actual not in paths:
            paths.append(actual)
    if not paths or len(paths) > 100:
        raise ValueError("Missing/unbounded Issue scope")
    return paths


def _trusted_issue_and_source(repo: Path, issue: int) -> tuple[str, str, list[str]]:
    """Run only pinned read operations under the independent signer process."""
    cleanenv = {"PATH": "/usr/bin:/bin", "HOME": "/root", "LANG": "C.UTF-8"}
    git = subprocess.run(
        ["/usr/bin/git", "-c", "safe.directory="+str(repo),
         "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=15, env=cleanenv)
    sha = git.stdout.strip()
    if not _HEX40.fullmatch(sha):
        raise ValueError("Invalid source SHA")
    gh = subprocess.run(
        ["/usr/bin/gh", "issue", "view", str(issue),
         "--repo", "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP",
         "--json", "body,state"],
        cwd=repo, capture_output=True, text=True, check=True, timeout=40,
        env=cleanenv)
    if len(gh.stdout) > 55000:
        raise ValueError("Issue payload exceeded limit")
    info = _strict_json(gh.stdout.encode())
    if info.get("state") != "OPEN" or not isinstance(info.get("body"), str):
        raise ValueError("Issue unavailable")
    body = info["body"]
    return sha, hashlib.sha256(body.encode()).hexdigest(), _scope_from_body(body)


def _trusted_signer_installation() -> bool:
    # Never execute scripts imported from a user-writable git checkout as root.
    path = Path(__file__).resolve()
    for ancestor in (path, *path.parents):
        stat_info = ancestor.stat(follow_symlinks=False)
        if stat_info.st_uid != 0 or stat_info.st_mode & 0o022:
            return False
    return True


def main() -> int:
    if Ed25519PrivateKey is None or serialization is None:
        raise SystemExit("Install reviewed cryptography package in root-owned signer environment")
    parser = argparse.ArgumentParser(description="ROOT-ONLY operator signing station, NEVER an MCP tool")
    parser.add_argument("operation", choices=["init", "approve"])
    parser.add_argument("--issue", type=int)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if (os.geteuid() != 0 or not sys.stdin.isatty() or not sys.stdout.isatty()
            or not _trusted_signer_installation()):
        parser.error("Privileged interactive root-owned installed signer required")
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
    # Do not import Python from the mutable repository into this privileged signer.
    pinned, issue_sha, scope = _trusted_issue_and_source(root_real, args.issue)
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
