#!/usr/bin/env python3
"""Check tracked worktree/index files and added diff lines, never print secrets."""

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


PRIVATE_KEY = re.compile(rb"(?m)^[ \t]*-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
CREDENTIAL = re.compile(
    rb"(?im)^[ \t]*(?:POSTGRES_PASSWORD|MQTT_PASSWORD|password)[ \t]*[:=][ \t]*([^\s#]+)"
)


def git(*args):
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, timeout=30
    ).stdout


def forbidden_path(name):
    path = PurePosixPath(name)
    return (
        (path.name == ".env" or path.name.startswith(".env."))
        and path.name != ".env.example"
    ) or path.suffix.lower() in {".key", ".p12", ".pfx", ".jks", ".keystore"} or (
        "secrets" in path.parts or path.name == "mosquitto.passwd"
    )


def contains_secret(data):
    if PRIVATE_KEY.search(data):
        return True
    for match in CREDENTIAL.finditer(data):
        value = match[1].strip(b"\"'")
        if value and not value.startswith((b"$", b"REPLACE_", b"<")):
            return True
    return False


def main():
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    failures = set()
    names = git("ls-files", "-z").decode().split("\0")
    for name in filter(None, names):
        if forbidden_path(name):
            failures.add(f"{name}: forbidden credential path")
        path = root / name
        if path.is_symlink():
            failures.add(f"{name}: symlink not scanned")
            continue
        if path.is_file() and contains_secret(path.read_bytes()):
            failures.add(f"{name}: secret signature in worktree")
        if contains_secret(git("show", f":{name}")):
            failures.add(f"{name}: secret signature in index")
    for args in (("diff", "--no-ext-diff", "--no-textconv", "--unified=0"),
                 ("diff", "--cached", "--no-ext-diff", "--no-textconv", "--unified=0")):
        added = b"\n".join(line[1:] for line in git(*args).splitlines()
                           if line.startswith(b"+") and not line.startswith(b"+++"))
        if contains_secret(added):
            failures.add("Git diff: secret signature in added lines")
    for failure in sorted(failures):
        print(f"FAIL: {failure}")
    print(f"{'FAIL' if failures else 'PASS'}: tracked files, index and Git diff secret checks")
    return bool(failures)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.SubprocessError) as error:
        print(f"FAIL: secret scan could not complete ({type(error).__name__})", file=sys.stderr)
        sys.exit(1)
