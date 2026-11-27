"""Synthetic regressions, disposable Git repositories, no keys or Docker required."""
import copy
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
import quality_gates as gates

FIXTURES = Path(__file__).parent / "fixtures" / "quality_gates"


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.safe = json.loads((FIXTURES / "safe.json").read_text())
        self.unsafe = json.loads((FIXTURES / "unsafe.json").read_text())
        self.missing = json.loads((FIXTURES / "missing.json").read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = (FIXTURES / "runtime.log").read_bytes()
        (self.root / "runtime.log").write_bytes(self.log)
        self.source = {"source_sha": "a" * 40, "candidate_sha256": "b" * 64}

    def receipt(self, rule):
        return {**self.source, "command": ["trusted-local-test", rule], "tool_version": "fixture 1",
                "exit_code": 0, "receipt_path": "runtime.log", "receipt_sha256": gates.digest(self.log),
                "observations": copy.deepcopy(self.safe.get(rule, {"checks_complete": True}))}

    def check(self, rule, entry):
        return gates.receipt_check(rule, entry, self.root, self.source)[0]

    def test_safe_unsafe_and_missing_for_each_security_rule(self):
        for rule in gates.VALIDATORS:
            with self.subTest(rule=rule):
                entry = self.receipt(rule)
                self.assertEqual(self.check(rule, entry), "PASS")
                entry["observations"] = self.unsafe[rule]
                self.assertEqual(self.check(rule, entry), "FAIL")
                entry["observations"] = self.missing[rule]
                self.assertEqual(self.check(rule, entry), "NOT_VERIFIED")
                self.assertEqual(self.check(rule, None), "NOT_RUN")

    def test_public_ca_and_multiple_public_certificates_are_safe(self):
        entry = self.receipt("SEC-KEY-MOUNT")
        entry["observations"]["clients"][1]["mounts"].extend([
            {"source": "/public/backend.pem", "target": "/certs/backend.pem", "read_only": True,
             "kind": "public_certificate"},
            {"source": "/public/server.crt", "target": "/certs/server.crt", "read_only": True,
             "kind": "public_certificate"}])
        self.assertEqual(self.check("SEC-KEY-MOUNT", entry), "PASS")

    def test_wrong_sources_private_key_modes_writable_and_directory_mounts(self):
        for field, value, expected in (("source", "/other/backend.key", "FAIL"),
                                      ("mode", "0644", "FAIL"), ("read_only", False, "FAIL"),
                                      ("source", "/keys/../gw-a.key", "FAIL")):
            with self.subTest(field=field):
                entry = self.receipt("SEC-KEY-MOUNT")
                entry["observations"]["clients"][1]["mounts"][1][field] = value
                self.assertEqual(self.check("SEC-KEY-MOUNT", entry), expected)
        entry = self.receipt("SEC-KEY-MOUNT")
        entry["observations"]["clients"][1]["mounts"] = [
            {"source": "/all-keys", "target": "/certs", "read_only": True, "kind": "directory"}]
        self.assertEqual(self.check("SEC-KEY-MOUNT", entry), "NOT_VERIFIED")

    def test_acl_warning_owner_group_unreadable_and_startup_error(self):
        for change in ({"acl_uid": 0}, {"acl_gid": 0}, {"acl_readable": False}, {"broker_uid": 0}):
            entry = self.receipt("MQTT-ACL-PERM")
            entry["observations"].update(change)
            self.assertEqual(self.check("MQTT-ACL-PERM", entry), "FAIL")
        for raw in ((FIXTURES / "acl-warning.log").read_bytes(),
                    b"Error: Unable to open acl_file /config/acl\n",
                    b"Error: Address already in use\n", b"chown: Read-only file system\n"):
            (self.root / "runtime.log").write_bytes(raw)
            entry = self.receipt("MQTT-ACL-PERM")
            entry["receipt_sha256"] = gates.digest(raw)
            self.assertEqual(self.check("MQTT-ACL-PERM", entry), "FAIL")

    def test_acl_positive_summary_and_expected_tls_denials_are_allowed(self):
        raw = (b"PASS: broker uid1883, ACL owner1883:1883 mode0600; no ownership/startup warnings\n"
               b"OpenSSL Error: certificate verify failed\n")
        (self.root / "runtime.log").write_bytes(raw)
        entry = self.receipt("MQTT-ACL-PERM")
        entry["receipt_sha256"] = gates.digest(raw)
        self.assertEqual(self.check("MQTT-ACL-PERM", entry), "PASS")

    def test_unrelated_suite_warning_does_not_fail_acl(self):
        raw = b"DeprecationWarning: datetime.utcnow() is deprecated\n"
        (self.root / "runtime.log").write_bytes(raw)
        entry = self.receipt("MQTT-ACL-PERM")
        entry["receipt_sha256"] = gates.digest(raw)
        self.assertEqual(self.check("MQTT-ACL-PERM", entry), "PASS")

    def test_network_static_only_failed_control_wsl_and_exposure(self):
        for change, expected in (({"runtime": False}, "NOT_VERIFIED"),
                                 ({"control_reachable": False}, "NOT_VERIFIED"),
                                 ({"representative": False, "network_context": "WSL2 internal only"}, "NOT_VERIFIED")):
            entry = self.receipt("NET-LOOPBACK")
            entry["observations"].update(change)
            self.assertEqual(self.check("NET-LOOPBACK", entry), expected)
        entry = self.receipt("NET-LOOPBACK")
        entry["observations"]["bindings"][0]["non_loopback_reachable"] = True
        self.assertEqual(self.check("NET-LOOPBACK", entry), "FAIL")
        entry = self.receipt("NET-LOOPBACK")
        entry["observations"]["bindings"][0]["host_ip"] = "::1"
        self.assertEqual(self.check("NET-LOOPBACK", entry), "PASS")

    def test_receipt_integrity_and_failed_command(self):
        for change, expected in (({"source_sha": "c" * 40}, "NOT_VERIFIED"),
                                 ({"candidate_sha256": "c" * 64}, "NOT_VERIFIED"),
                                 ({"receipt_sha256": "c" * 64}, "NOT_VERIFIED"),
                                 ({"exit_code": 1}, "FAIL"),
                                 ({"exit_code": False}, "NOT_VERIFIED"),
                                 ({"tool_version": ""}, "NOT_VERIFIED"),
                                 ({"command": "test | true"}, "NOT_VERIFIED")):
            entry = self.receipt("NET-LOOPBACK")
            entry.update(change)
            self.assertEqual(self.check("NET-LOOPBACK", entry), expected)

    def test_malformed_observations_do_not_escape_json_reporting(self):
        for value in ([], "PASS", None, {"runtime_inventory_complete": True, "clients": [None]}):
            entry = self.receipt("SEC-KEY-MOUNT")
            entry["observations"] = value
            self.assertEqual(self.check("SEC-KEY-MOUNT", entry), "NOT_VERIFIED")

    def test_no_receipt_command_is_executed_or_echoed(self):
        entry = self.receipt("MQTT-ACL-PERM")
        entry["command"] = ["sh", "-c", "touch SHOULD_NOT_EXIST password=do-not-print"]
        with patch.object(subprocess, "run", side_effect=AssertionError("executed")):
            status, _, metadata = gates.receipt_check("MQTT-ACL-PERM", entry, self.root, self.source)
        self.assertEqual(status, "PASS")
        self.assertNotIn("do-not-print", json.dumps(metadata))
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_receipt_symlinks_escapes_empty_and_secrets_fail_closed(self):
        (self.root / "alias.log").symlink_to(self.root / "runtime.log")
        (self.root / "alias-dir").symlink_to(self.root, target_is_directory=True)
        for name in ("../runtime.log", "/etc/passwd", "alias.log", "alias-dir/runtime.log"):
            entry = self.receipt("NET-LOOPBACK")
            entry["receipt_path"] = name
            self.assertEqual(self.check("NET-LOOPBACK", entry), "NOT_VERIFIED")
        for raw in (b"", b"POSTGRES_PASSWORD=synthetic-do-not-log\n"):
            (self.root / "runtime.log").write_bytes(raw)
            entry = self.receipt("NET-LOOPBACK")
            entry["receipt_sha256"] = gates.digest(raw)
            self.assertEqual(self.check("NET-LOOPBACK", entry), "NOT_VERIFIED")


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.write("README.md", "baseline\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return gates.git(self.root, *args)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def scan(self):
        return gates.evaluate(self.root, self.base)

    def rule(self, name):
        return next(r for r in self.scan()["results"] if r["rule_id"] == name)

    def test_docs_fixture_routes_without_docker_or_module_receipts(self):
        self.write("README.md", (FIXTURES / "docs-only.md").read_text())
        report = self.scan()
        self.assertEqual(report["risks"], ["all"])
        self.assertEqual(report["auto_check"], "AUTO_CHECK_PASS")
        self.assertEqual(report["human_security_review"], "NOT_REQUIRED")
        self.assertEqual(self.rule("NET-LOOPBACK")["status"], "NOT_RUN")
        self.assertFalse(report["ready_to_merge"])

    def test_module_and_security_routing(self):
        for name, risks in (("firmware/main.c", {"all", "firmware"}),
                            ("backend-go/main.go", {"all", "backend"}),
                            ("deploy/compose.yaml", {"all", "infra", "mqtt"}),
                            ("scripts/credentials.py", {"all", "security", "tooling"})):
            self.assertEqual(gates.route([name]), risks)
        self.write("deploy/compose.yaml", "services: {}\n")
        report = self.scan()
        self.assertEqual(report["auto_check"], "BLOCKED")
        self.assertEqual(report["human_security_review"], "HUMAN_SECURITY_REVIEW_PENDING")
        for name in gates.VALIDATORS:
            self.assertEqual(self.rule(name)["status"], "NOT_RUN")

    def test_standards_policy_documents_require_tooling_and_security(self):
        for name in ("docs/development/firmware/C_CODING_STANDARD_V2.md",
                     "docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md"):
            self.assertEqual(gates.route([name]), {"all", "tooling", "security"})

    def test_harness_control_paths_require_tooling_and_security(self):
        controls = (
            "AGENTS.md", "firmware/AGENTS.md", ".github/copilot-instructions.md",
            ".github/instructions/backend.instructions.md", ".agents/agents/harness-coordinator.md",
            ".agents/agents/c-structural-refactor.md",
            "docs/development/c-clean-code-refactoring-standard.md",
            "docs/development/ccars-graph-first-adoption.md",
            ".agents/skills/example/SKILL.md", ".agent-harness/worker.md", ".agent-harness/auditor.md",
            ".agent-harness/security/provider-decision.md", ".codex/config.toml",
            "docs/development/harness-fast-lane.md", "docs/development/harness-quality-gates.md",
            "docs/development/AI_TASK_START_PROTOCOL.md", "docs/development/agent-harness-firmware.md",
            "docs/development/agy-supervised-pilot.md", "scripts/agent_harness/scope.py",
            "scripts/agent_harness/p1/pilot.py",
        )
        for name in controls:
            with self.subTest(path=name):
                self.assertEqual(gates.route([name]), {"all", "tooling", "security"})

    def test_contract_and_adr_markdown_require_security_routing(self):
        for name in ("contracts/mqtt/topics.md", "contracts/mqtt/semantic-rules.md",
                     "contracts/mqtt/schemas/schedule.schema.json", "docs/adr/0002-mqtt-5.md"):
            with self.subTest(path=name):
                self.assertEqual(gates.route([name]), {"all", "infra", "mqtt", "security"})
        for name in ("contracts/api/contract-semantics.md", "contracts/radio-mac/specification.md",
                     "contracts/v1/overview.md", "contracts/README.md", "docs/adr/0003-esp-idf-v6-1.md",
                     "docs/adr/README.md"):
            with self.subTest(path=name):
                self.assertEqual(gates.route([name]), {"all", "security"})

    def test_contract_and_adr_only_cli_blocks_without_receipts(self):
        authorities = ("contracts/mqtt/topics.md", "contracts/mqtt/semantic-rules.md",
                       "contracts/api/contract-semantics.md", "docs/adr/0002-mqtt-5.md")
        for name in authorities:
            self.write(name, "Baseline authority\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "authority baseline")
        base = self.git("rev-parse", "HEAD").decode().strip()
        for name in authorities:
            for staged in (False, True):
                with self.subTest(path=name, staged=staged):
                    self.write(name, "Changed authority\nStatus: DRAFT\n")
                    if staged:
                        self.git("add", name)
                    try:
                        result = subprocess.run(
                            [sys.executable, gates.__file__, "--repo", str(self.root), "--base", base],
                            capture_output=True, text=True, timeout=30)
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        report = json.loads(result.stdout)
                        self.assertEqual(report["changed_paths"], [name])
                        self.assertEqual(report["auto_check"], "BLOCKED")
                        self.assertIn("security", report["risks"])
                        self.assertEqual(next(r for r in report["results"] if r["rule_id"] == "SECURITY-CHECK")["status"], "NOT_RUN")
                        self.assertEqual(report["human_security_review"], "HUMAN_SECURITY_REVIEW_PENDING")
                        self.assertFalse(report["ready_to_merge"])
                    finally:
                        self.write(name, "Baseline authority\n")
                        if staged:
                            self.git("add", name)

    def test_control_only_cli_blocks_without_required_receipts(self):
        controls = ("AGENTS.md", ".agents/agents/harness-coordinator.md",
                    ".agent-harness/auditor.md", ".github/copilot-instructions.md",
                    "docs/development/harness-fast-lane.md", "docs/development/harness-quality-gates.md",
                    ".agents/agents/c-structural-refactor.md",
                    "docs/development/c-clean-code-refactoring-standard.md",
                    "docs/development/ccars-graph-first-adoption.md")
        for name in controls:
            self.write(name, "Baseline policy\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "policy baseline")
        base = self.git("rev-parse", "HEAD").decode().strip()
        for name in controls:
            for staged in (False, True):
                with self.subTest(path=name, staged=staged):
                    self.write(name, "Changed policy\n")
                    if staged:
                        self.git("add", name)
                    result = subprocess.run(
                        [sys.executable, gates.__file__, "--repo", str(self.root), "--base", base],
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report["changed_paths"], [name])
                    self.assertEqual(report["risks"], ["all", "security", "tooling"])
                    for rule in ("TOOLING-CHECK", "SECURITY-CHECK"):
                        self.assertEqual(next(r for r in report["results"] if r["rule_id"] == rule)["status"], "NOT_RUN")
                    self.assertEqual(report["human_security_review"], "HUMAN_SECURITY_REVIEW_PENDING")
                    self.assertFalse(report["ready_to_merge"])
                    self.write(name, "Baseline policy\n")
                    if staged:
                        self.git("add", name)

    def test_ordinary_markdown_only_cli_keeps_fast_path(self):
        docs = ("README.md", "docs/development/notes.md", "docs/architecture/security-overview.md",
                "firmware/README.md", "backend-go/README.md", "deploy/README.md",
                ".github/pull_request_template.md")
        for name in docs:
            with self.subTest(path=name):
                self.assertEqual(gates.route([name]), {"all"})
        self.write("docs/development/notes.md", "Ordinary documentation update\n")
        result = subprocess.run(
            [sys.executable, gates.__file__, "--repo", str(self.root), "--base", self.base],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["risks"], ["all"])
        self.assertEqual(report["auto_check"], "AUTO_CHECK_PASS")
        self.assertEqual(report["human_security_review"], "NOT_REQUIRED")
        self.assertTrue(all(r["status"] == "NOT_RUN" for r in report["results"]
                            if r["rule_id"] not in ("SECRET-SCAN", "DIFF-CHECK")))

    def test_harness_security_fixtures_do_not_select_live_infrastructure(self):
        self.assertEqual(gates.route(["tests/agent_harness/fixtures/quality_gates/acl-warning.log"]),
                         {"all", "tooling", "security"})

    def test_hostile_git_fsmonitor_is_never_executed(self):
        with tempfile.TemporaryDirectory() as outside:
            hook = Path(outside) / "monitor.sh"
            marker = Path(outside) / "executed"
            hook.write_text("#!/bin/sh\ntouch " + shlex.quote(str(marker)) + "\n")
            hook.chmod(0o700)
            self.git("config", "core.fsmonitor", str(hook))
            self.assertEqual(self.scan()["auto_check"], "AUTO_CHECK_PASS")
            self.assertFalse(marker.exists())

    def test_git_conversion_filters_are_blocked_before_diff(self):
        self.write("data.txt", "baseline\n")
        self.write(".gitattributes", "data.txt filter=probe\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
        with tempfile.TemporaryDirectory() as outside:
            script = Path(outside) / "filter.sh"
            marker = Path(outside) / "executed"
            script.write_text("#!/bin/sh\ntouch " + shlex.quote(str(marker)) + "\ncat\n")
            script.chmod(0o700)
            for key in ("filter.probe.clean", "filter.probe.process"):
                self.git("config", key, str(script))
                self.write("data.txt", "changed\n")
                with self.assertRaises(ValueError):
                    self.scan()
                self.assertFalse(marker.exists())
                self.git("config", "--unset", key)

    def test_trusted_system_git_lfs_does_not_block_evaluation(self):
        with tempfile.TemporaryDirectory() as outside:
            sys_cfg = Path(outside) / "system.gitconfig"
            sys_cfg.write_text(
                '[filter "lfs"]\n'
                '\tclean = git-lfs clean -- %f\n'
                '\tprocess = git-lfs filter-process\n'
                '\tsmudge = git-lfs smudge -- %f\n'
            )
            with patch.dict(os.environ, {"GIT_CONFIG_SYSTEM": str(sys_cfg)}):
                self.write("docs/development/notes.md", "Documentation update with system LFS present\n")
                report = self.scan()
                self.assertEqual(report["risks"], ["all"])
                self.assertEqual(report["auto_check"], "AUTO_CHECK_PASS")

                cmd = [sys.executable, gates.__file__, "--repo", str(self.root), "--base", self.base]
                done = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                      env={**os.environ, "GIT_CONFIG_SYSTEM": str(sys_cfg)})
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_system_filter_config_inside_worktree_is_blocked_with_value_error(self):
        inside_cfg = self.root / "system.gitconfig"
        inside_cfg.write_text(
            '[filter "lfs"]\n'
            '\tclean = git-lfs clean -- %f\n'
            '\tprocess = git-lfs filter-process\n'
            '\tsmudge = git-lfs smudge -- %f\n'
        )
        with patch.dict(os.environ, {"GIT_CONFIG_SYSTEM": str(inside_cfg)}):
            with self.assertRaises(ValueError):
                gates.git_command(self.root, "diff", "HEAD")
            self.write("docs/development/notes.md", "Documentation update with inside config\n")
            with self.assertRaises(ValueError):
                self.scan()
            cmd = [sys.executable, gates.__file__, "--repo", str(self.root), "--base", self.base]
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                  env={**os.environ, "GIT_CONFIG_SYSTEM": str(inside_cfg)})
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            self.assertEqual(json.loads(done.stdout)["status"], "NOT_VERIFIED")

    def test_hidden_index_flags_block_routing_bypass(self):
        self.write("deploy/compose.yaml", "baseline\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
        for flag, undo in (("--assume-unchanged", "--no-assume-unchanged"),
                           ("--skip-worktree", "--no-skip-worktree")):
            self.git("update-index", flag, "deploy/compose.yaml")
            self.write("deploy/compose.yaml", "unsafe modified infrastructure\n")
            with self.assertRaises(ValueError):
                self.scan()
            self.git("update-index", undo, "deploy/compose.yaml")

    def test_cli_deep_json_returns_machine_readable_blocked_result(self):
        with tempfile.TemporaryDirectory() as outside:
            manifest = Path(outside) / "manifest.json"
            manifest.write_text('{"checks":{"NET-LOOPBACK":' + '[' * 30000 + '0' + ']' * 30000 + '}}')
            result = subprocess.run(
                [sys.executable, gates.__file__, "--repo", str(self.root), "--base", self.base,
                 "--evidence-dir", outside, "--manifest", "manifest.json"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2, f"Expected rc=2, got rc={result.returncode}. stdout: {result.stdout}, stderr: {result.stderr}")
            self.assertEqual(json.loads(result.stdout)["status"], "NOT_VERIFIED")
            self.assertNotIn("Traceback", result.stderr)

    def test_secret_scan_safe_unsafe_and_unavailable(self):
        self.write("public.crt", "-----BEGIN CERTIFICATE-----\npublic fixture\n")
        self.write(".env.example", "POSTGRES_PASSWORD=REPLACE_WITH_LOCAL_PASSWORD\n")
        self.assertEqual(self.rule("SECRET-SCAN")["status"], "PASS")
        self.write("notes.txt", "-----BEGIN " + "PRIVATE KEY-----\n")
        self.assertEqual(self.rule("SECRET-SCAN")["status"], "FAIL")
        self.write("notes.txt", "safe\n")
        with patch.object(gates, "safe_read", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                self.scan()

    def test_known_key_paths_never_opened(self):
        self.write("server.key", "not a real key")
        original = gates.safe_read
        def checked(root, name):
            self.assertNotEqual(name, "server.key")
            return original(root, name)
        with patch.object(gates, "safe_read", side_effect=checked):
            report = self.scan()
        self.assertEqual(next(r for r in report["results"] if r["rule_id"] == "SECRET-SCAN")["status"], "FAIL")
        self.assertNotIn("not a real key", json.dumps(report))

    def test_staged_secret_hidden_by_worktree_and_committed_unchanged_secret(self):
        self.write("settings.txt", "MQTT_PASSWORD=synthetic-hidden-value\n")
        self.git("add", "settings.txt")
        self.write("settings.txt", "safe worktree\n")
        self.assertEqual(self.rule("SECRET-SCAN")["status"], "FAIL")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "staged fixture")
        self.assertEqual(self.rule("SECRET-SCAN")["status"], "FAIL")
        self.assertNotIn("synthetic-hidden-value", json.dumps(self.scan()))

    def test_ignored_secret_symlink_nonregular_and_budget(self):
        self.write(".gitignore", "private/\n")
        self.write("private/server.key", "local-only material")
        self.assertEqual(self.rule("SECRET-SCAN")["status"], "PASS")
        (self.root / "escape").symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            self.scan()
        (self.root / "escape").unlink()
        with patch.object(gates, "MAX_BYTES", 2):
            with self.assertRaises(ValueError):
                self.scan()

    def test_fingerprint_changes_for_stage_worktree_untracked_and_head(self):
        one, _ = gates.inventory(self.root, self.base)
        self.write("README.md", "changed\n")
        two, _ = gates.inventory(self.root, self.base)
        self.git("add", "README.md")
        three, _ = gates.inventory(self.root, self.base)
        self.write("new.txt", "new\n")
        four, _ = gates.inventory(self.root, self.base)
        self.assertEqual(len({r["candidate_sha256"] for r in (one, two, three, four)}), 4)
        with patch.object(gates, "inventory", side_effect=[(one, []), (two, [])]):
            with self.assertRaises(ValueError):
                self.scan()

    def test_required_receipts_pass_fail_and_stale_source_block_readiness(self):
        self.write("deploy/compose.yaml", "services: {}\n")
        with tempfile.TemporaryDirectory() as external:
            evidence = Path(external)
            raw = (FIXTURES / "runtime.log").read_bytes()
            (evidence / "runtime.log").write_bytes(raw)
            source, _ = gates.inventory(self.root, self.base)
            safe = json.loads((FIXTURES / "safe.json").read_text())
            checks = {}
            for rule, (_, risk) in gates.REGISTRY.items():
                if risk in ("infra", "mqtt"):
                    checks[rule] = {**source, "command": ["trusted-host-test"], "tool_version": "test 1",
                                    "exit_code": 0, "receipt_path": "runtime.log",
                                    "receipt_sha256": gates.digest(raw),
                                    "observations": safe.get(rule, {"checks_complete": True})}
            def evaluate():
                (evidence / "manifest.json").write_text(json.dumps({"checks": checks}))
                return gates.evaluate(self.root, self.base, "manifest.json", evidence)
            report = evaluate()
            self.assertEqual(report["auto_check"], "AUTO_CHECK_PASS")
            self.assertEqual(report["human_security_review"], "HUMAN_SECURITY_REVIEW_PENDING")
            self.assertFalse(report["ready_to_merge"])
            checks["MQTT-ACL-PERM"]["exit_code"] = 1
            self.assertEqual(evaluate()["auto_check"], "BLOCKED")
            checks["MQTT-ACL-PERM"]["exit_code"] = 0
            self.write("README.md", "changed after evidence\n")
            report = evaluate()
            self.assertEqual(report["auto_check"], "BLOCKED")
            self.assertEqual(next(r for r in report["results"] if r["rule_id"] == "MQTT-ACL-PERM")["status"], "NOT_VERIFIED")

    def test_schema_password_field_is_not_a_credential(self):
        self.write("schema.yaml", 'password:\n  type: "string"\n')
        self.write("generate.py", '    "POSTGRES_PASSWORD": secrets.token_hex(24)\n')
        self.assertEqual(self.rule("SECRET-SCAN")["status"], "PASS")

    def test_duplicate_manifest_keys_rejected(self):
        self.write("manifest.json", '{"checks": {}, "checks": {}}')
        with self.assertRaises(ValueError):
            gates.evaluate(self.root, self.base, "manifest.json", self.root)

    def test_cli_exit_status_redaction_and_fingerprint(self):
        command = [sys.executable, gates.__file__, "--repo", str(self.root), "--base", self.base]
        for args, code in (([], 0), (["--fingerprint-only"], 0), (["--base", "missing"], 2)):
            result = subprocess.run(command + args, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            json.loads(result.stdout)
        self.write("settings.txt", "POSTGRES_PASSWORD=synthetic-cli-private\n")
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)


class StandardsCheckV2Tests(unittest.TestCase):
    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        gates.git(self.root, "init", "-q")
        std_rel = "docs/development/firmware/C_CODING_STANDARD_V2.md"
        actual_std = Path(__file__).resolve().parents[2] / std_rel
        self.write(std_rel, actual_std.read_text(encoding="utf-8"))
        self.write("firmware/test.c", "int val = 42;\n")
        gates.git(self.root, "add", ".")
        gates.git(self.root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline")
        self.base = gates.git(self.root, "rev-parse", "HEAD").decode().strip()
        self.write("firmware/test.c", "int val = 99;\n")
        self.source, _ = gates.inventory(self.root, self.base)
        self.external = tempfile.TemporaryDirectory()
        self.addCleanup(self.external.cleanup)
        self.evidence = Path(self.external.name)
        self.log = b"Synthetic quality gates log\n"
        (self.evidence / "checks.log").write_bytes(self.log)

        from standards_policy import select_rules, digest
        self.selection = select_rules(self.root, ["firmware/test.c"], base=self.base, version=2,
                                      candidate_sha256=self.source["candidate_sha256"])
        self.hashes = {r["rule_id"]: r["rule_sha256"] for r in self.selection["rules"]}
        self.receipt = {**self.source, "command": ["test"], "tool_version": "test", "exit_code": 0,
                        "receipt_path": "checks.log", "receipt_sha256": digest(self.log),
                        "observations": {"checks_complete": True}}
        self.edit = {
            "source_sha": self.source["source_sha"],
            "base_sha": self.base,
            "candidate_sha256": self.source["candidate_sha256"],
            "selection_sha256": self.selection["selection_sha256"],
            "prompt_sha256": digest(b"dummy prompt"),
            "schema_version": 2,
            "selected_ids": self.selection["selected_ids"],
            "rule_hashes": self.hashes,
            "partition_count": len(self.selection["partitions"]),
            "injected_partitions": [
                {"partition_index": p["partition_index"], "partition_hash": p["partition_hash"],
                 "rule_ids": p["selected_ids"], "prompt_bytes": p["prompt_bytes"]}
                for p in self.selection["partitions"]
            ],
            "assigned_report_scope": self.selection["partitions"][0]["selected_ids"],
        }
        (self.evidence / "edit.json").write_text(json.dumps(self.edit), encoding="utf-8")

        self.payload = {"selection": self.selection, "rules": {}}
        for r in self.selection["rules"]:
            self.payload["rules"][r["rule_id"]] = {
                **self.receipt,
                "observations": {"checks_complete": True,
                                 "selection_sha256": self.selection["selection_sha256"],
                                 "rule_sha256": r["rule_sha256"]}
            }

        for role in ("worker", "auditor"):
            part_reports = []
            for p in self.selection["partitions"]:
                rep = {
                    "status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": self.source["changed_paths"],
                    "selection_sha256": p["partition_hash"],
                    "rule_results": [
                        {"rule_id": r["rule_id"], "rule_sha256": r["rule_sha256"],
                         "status": "PASS", "evidence": [{"receipt_path": "checks.log", "receipt_sha256": digest(self.log)}],
                         "reason": "PASS evidence verified"}
                        for r in p["rules"]
                    ]
                }
                part_reports.append({
                    "partition_index": p["partition_index"],
                    "partition_hash": p["partition_hash"],
                    "selected_ids": p["selected_ids"],
                    "report": rep,
                })
            record = {
                "role": role, "agent_id": f"{role}-agent-1",
                "schema_version": 2,
                "selection_sha256": self.selection["selection_sha256"],
                "selected_ids": self.selection["selected_ids"],
                "rule_hashes": self.hashes,
                "edit_receipt_path": "edit.json",
                "evidence_inventory": {"checks.log": digest(self.log)},
                "partition_reports": part_reports,
            }
            rec_bytes = json.dumps(record).encode("utf-8")
            (self.evidence / f"{role}.json").write_bytes(rec_bytes)
            self.payload[role] = {**self.receipt, "receipt_path": f"{role}.json", "receipt_sha256": digest(rec_bytes)}

    def test_standards_check_v2_partitioned_reports_pass(self):
        selected, rows, status, reason = gates.standards_check(self.root, self.base, self.source, self.payload, self.evidence)
        self.assertEqual(status, "PASS")
        self.assertEqual(len(rows), len(self.selection["selected_ids"]))
        self.assertTrue(all(r["status"] == "PASS" for r in rows))

    def test_standards_check_v2_missing_partition_report_blocks(self):
        # Create an incomplete worker record missing partition reports
        worker_rec = json.loads((self.evidence / "worker.json").read_text(encoding="utf-8"))
        worker_rec["partition_reports"] = []
        raw = json.dumps(worker_rec).encode("utf-8")
        (self.evidence / "worker.json").write_bytes(raw)
        self.payload["worker"]["receipt_sha256"] = gates.digest(raw)
        _, _, status, _ = gates.standards_check(self.root, self.base, self.source, self.payload, self.evidence)
        self.assertEqual(status, "NOT_VERIFIED")

    def test_standards_check_v2_partial_pre_edit_injection_blocks(self):
        edit = dict(self.edit)
        edit["injected_partitions"] = []
        (self.evidence / "edit.json").write_text(json.dumps(edit), encoding="utf-8")
        _, _, status, _ = gates.standards_check(self.root, self.base, self.source, self.payload, self.evidence)
        self.assertEqual(status, "NOT_VERIFIED")

    def test_receipt_check_rejects_stale_diff_sha_and_waived_or_skipped_flags(self):
        source = {**self.source, "diff_sha256": "d" * 64}
        entry = {**self.receipt, "diff_sha256": "e" * 64}
        status, reason, _ = gates.receipt_check("TOOLING-CHECK", entry, self.evidence, source)
        self.assertEqual(status, "NOT_VERIFIED")
        self.assertIn("diff_sha256", reason)
        for flag in ("waived", "owner_waived", "commit_only", "skipped"):
            flagged = {**self.receipt, flag: True}
            status_f, _, _ = gates.receipt_check("TOOLING-CHECK", flagged, self.evidence, source)
            self.assertEqual(status_f, "NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
