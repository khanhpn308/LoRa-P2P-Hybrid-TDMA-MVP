"""P06 Observability, Failure Attribution, Safe Cleanup & Clean Handoff tests."""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))

import check as check_mod
import feature_state as fs
import observability as obs
from p1 import cli as p1_cli
from p1.process import execute_checked
from p1.state import Journal, StateConflict
import pr_review as pr_rev


def _git(repo: pathlib.Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return p.stdout.strip()


class ObservabilityAndHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, timeout=15)
        _git(self.repo, "config", "user.name", "Harness Test")
        _git(self.repo, "config", "user.email", "test@example.invalid")

        real_repo = pathlib.Path(__file__).resolve().parents[2]
        for rel in (
            "AGENTS.md",
            "firmware/esp-idf-version.txt",
            ".go-version",
            "scripts/verify_structure.py",
            "scripts/harness_doctor.py",
            "docs/development/harness-fast-lane.md",
            "docs/development/harness-quality-gates.md",
            "docs/development/AI_TASK_START_PROTOCOL.md",
            "docs/development/agent-harness-firmware.md",
            "docs/development/agy-supervised-pilot.md",
            "docs/development/c-clean-code-refactoring-standard.md",
            "docs/development/ccars-graph-first-adoption.md",
            "docs/development/firmware/C_CODING_STANDARD_V2.md",
            "docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md",
            "docs/adr/0004-pure-cad-csma-ca-mac.md",
        ):
            src = real_repo / rel
            if src.is_file():
                dst = self.repo / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        for d_rel in ("firmware/sensor_node", "firmware/gateway_master", "backend-go", "clients", "contracts"):
            (self.repo / d_rel).mkdir(parents=True, exist_ok=True)
            (self.repo / d_rel / ".keep").write_text("ok\n", encoding="utf-8")
        (self.repo / "README.md").write_text("baseline\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "initial")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD")
        self.branch = "feature/433-p06-test"
        _git(self.repo, "checkout", "-qb", self.branch)

        self.host_dir = self.root / "host"
        self.host_dir.mkdir(mode=0o700)
        self.journal_path = self.host_dir / "state.sqlite"
        self.issue_data = {
            "title": "P06 test issue",
            "body": "## Target Directories (allowed paths)\n- `scripts/verify_structure.py`\n- `README.md`\n",
            "scope": ("scripts/verify_structure.py", "README.md"),
            "issue_sha256": "a" * 64,
        }

    def test_secret_redaction_and_fail_closed_check_runner(self) -> None:
        raw_secrets = (
            "POSTGRES_PASSWORD=super_secret_pw_123\n"
            "Authorization: Bearer abcdef1234567890xyz\n"
            "url=postgres://admin:topsecret99@db.local:5432/lora\n"
            "token=ghp_1234567890abcdef1234567890abcdef1234\n"
            "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBALeaks\n-----END RSA PRIVATE KEY-----\n"
            "safe_placeholder=$POSTGRES_PASSWORD\n"
            "safe_template=REPLACE_ME\n"
        )
        redacted, was_redacted, was_truncated = obs.redact_text(raw_secrets)
        self.assertTrue(was_redacted)
        self.assertFalse(was_truncated)
        for secret_val in ("super_secret_pw_123", "abcdef1234567890xyz", "topsecret99", "ghp_1234567890abcdef1234567890abcdef1234", "MIIBOgIBAAJBALeaks"):
            self.assertNotIn(secret_val, redacted)
        self.assertIn("$POSTGRES_PASSWORD", redacted)
        self.assertIn("REPLACE_ME", redacted)

        # Inject a check command that prints a synthetic token and exits 0; check.py MUST fail closed and redact!
        (self.repo / "scripts/verify_structure.py").write_text(
            "print('ghp_1234567890abcdef1234567890abcdef1234')\n",
            encoding="utf-8",
        )
        ev_dir = self.host_dir / "ev_secret"
        res = check_mod.run_checks(
            self.repo,
            base_sha=self.base_sha,
            profile="quick",
            evidence_dir=ev_dir,
            run_quality_gates=False,
            journal_path=self.journal_path,
            issue=433,
            run_id="run-secret-1",
        )
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["exit_code"], 1)
        log_text = (ev_dir / "check_verify-structure.log").read_text(encoding="utf-8")
        self.assertNotIn("ghp_1234567890abcdef1234567890abcdef1234", log_text)
        sigs = obs.query_signals(self.journal_path, issue=433)
        self.assertGreaterEqual(len(sigs), 1)
        vs_sig = next(s for s in sigs if s["check_id"] == "verify-structure")
        self.assertEqual(vs_sig["status"], "FAIL")
        self.assertNotIn("ghp_1234567890abcdef1234567890abcdef1234", json.dumps(sigs))

    def test_json_key_value_and_nested_credential_redaction(self) -> None:
        payload = {
            "password": "plain_pw_no_prefix",
            "input_tokens": 40599,
            "metadata": {
                "api_key": "raw_api_key_value",
                "credentials": {
                    "username": "gw-a",
                    "passcode": "nested_secret_value",
                    "pin": 9876,
                    "placeholder": "$MQTT_PASSWORD",
                },
                "auth": [
                    {"token": "nested_list_token_abc", "template": "REPLACE_ME"},
                ],
                "notes": "connect postgres://dbuser:nested_dsn_pw@db.local:5432/app",
                "ghp_1234567890abcdef1234567890abcdef1234": "key_was_secret",
            },
        }
        redacted = obs.redact_data(payload)
        serialized = json.dumps(redacted)
        for secret in (
            "plain_pw_no_prefix",
            "raw_api_key_value",
            "nested_secret_value",
            "9876",
            "nested_list_token_abc",
            "nested_dsn_pw",
            "ghp_1234567890abcdef1234567890abcdef1234",
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["input_tokens"], 40599)
        self.assertEqual(redacted["metadata"]["api_key"], "[REDACTED]")
        self.assertEqual(redacted["metadata"]["credentials"]["placeholder"], "$MQTT_PASSWORD")
        self.assertEqual(redacted["metadata"]["auth"][0]["template"], "REPLACE_ME")

        with Journal(self.journal_path) as j:
            j.record_signal(
                signal_type="process",
                category="check",
                owning_domain="harness",
                status="FAIL",
                issue=433,
                check_id="nested-json-test",
                evidence_ref=payload,
            )
            rows = j.query_signals(issue=433, limit=5)
        db_serialized = json.dumps(rows)
        for secret in (
            "plain_pw_no_prefix",
            "raw_api_key_value",
            "nested_secret_value",
            "9876",
            "nested_list_token_abc",
            "nested_dsn_pw",
            "ghp_1234567890abcdef1234567890abcdef1234",
        ):
            self.assertNotIn(secret, db_serialized)
        self.assertEqual(rows[0]["evidence_ref"]["input_tokens"], 40599)
        self.assertEqual(rows[0]["evidence_ref"]["password"], "[REDACTED]")

    def test_truncation_retention_and_immutable_checkpoint_preservation(self) -> None:
        long_text = "A" * 6000
        bounded, _, truncated = obs.redact_text(long_text, max_bytes=512)
        self.assertTrue(truncated)
        self.assertLessEqual(len(bounded.encode("utf-8")), 512)
        self.assertTrue(bounded.endswith("...[TRUNCATED]"))

        ckpt = fs.session_checkpoint(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            next_action="Verify signal retention keeps checkpoints intact",
            base_sha=self.base_sha,
        )
        with Journal(self.journal_path) as j:
            for idx in range(25):
                j.record_signal(
                    signal_type="process",
                    category="check",
                    owning_domain="harness",
                    status="PASS",
                    issue=433,
                    check_id=f"c-{idx}",
                    finding=f"msg-{idx}",
                    excerpt="X" * 5000,
                    max_signals=10,
                )
            rows = j.query_signals(issue=433, limit=50)
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[0]["check_id"], "c-24")
            self.assertLessEqual(len(rows[0]["excerpt"]), 4000)
            # Immutable checkpoint must remain intact after signal pruning
            latest = j.latest_checkpoint(433)
            self.assertIsNotNone(latest)
            self.assertEqual(latest["checkpoint_id"], ckpt["checkpoint_id"])

    def test_symlink_and_in_repo_journal_rejected(self) -> None:
        sym_journal = self.host_dir / "sym.sqlite"
        sym_journal.symlink_to(self.host_dir / "real.sqlite")
        with self.assertRaises(obs.ObservabilityError):
            obs.record_process_signal(
                journal_path=sym_journal,
                category="check",
                owning_domain="harness",
                status="PASS",
                issue=433,
            )

        in_repo_journal = self.repo / "state.sqlite"
        with self.assertRaises(ValueError):
            check_mod.run_checks(
                self.repo,
                base_sha=self.base_sha,
                profile="quick",
                evidence_dir=self.host_dir / "ev_inrepo",
                run_quality_gates=False,
                journal_path=in_repo_journal,
                issue=433,
            )

    def test_runtime_signal_map_separates_captured_from_unavailable(self) -> None:
        obs.record_process_signal(
            journal_path=self.journal_path,
            signal_type="process",
            category="check",
            owning_domain="harness",
            status="PASS",
            captured=True,
            issue=433,
            check_id="verify-structure",
        )
        rmap = obs.collect_runtime_signal_map(
            repo=self.repo,
            journal_path=self.journal_path,
            issue=433,
        )
        self.assertEqual(rmap["captured_count"], 1)
        unavailable_ids = {item["signal_id"] for item in rmap["unavailable_or_planned_signals"]}
        self.assertIn("uart_radio", unavailable_ids)
        self.assertIn("mqtt_broker", unavailable_ids)
        self.assertIn("db_postgres", unavailable_ids)
        self.assertIn("web_ui", unavailable_ids)
        for item in rmap["unavailable_or_planned_signals"]:
            self.assertFalse(item["captured"])
            self.assertEqual(item["status"], "NOT_VERIFIED")

    def test_golden_journey_failure_injection_attribution_repair_and_rerun(self) -> None:
        res = obs.run_golden_journey(source_repo=pathlib.Path(__file__).resolve().parents[2], issue=433)
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["before_status"], "PASS")
        self.assertEqual(res["injected_failure_status"], "FAIL")
        self.assertEqual(res["after_repair_status"], "PASS")
        self.assertFalse(res["secret_leaked"])
        self.assertEqual(res["diagnosis_top"]["check_id"], "verify-structure")
        self.assertEqual(res["diagnosis_top"]["owning_domain"], "foundation")
        self.assertEqual(res["resumed_status"], "ALL_UNITS_PASSING_LOCAL")
        self.assertEqual(res["hil_rf"], "NOT_VERIFIED")

    def test_golden_journey_reproducible_under_headless_ci_runner_env(self) -> None:
        # Simulate CI runner without agy/codex or GitHub auth tokens while keeping python3/git/gh available.
        runner_bin = self.host_dir / "ci_runner_bin"
        runner_bin.mkdir()
        for tool_name in ("python3", "git", "gh", "sh"):
            found = shutil.which(tool_name)
            if found:
                (runner_bin / tool_name).symlink_to(found)
        empty_home = self.host_dir / "ci_home"
        empty_home.mkdir()
        clean_env = {
            "PATH": str(runner_bin),
            "HOME": str(empty_home),
        }
        with mock.patch.dict(os.environ, clean_env, clear=False):
            for secret_var in ("GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR"):
                os.environ.pop(secret_var, None)
            res = obs.run_golden_journey(source_repo=pathlib.Path(__file__).resolve().parents[2], issue=433)
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["before_status"], "PASS")
        self.assertEqual(res["injected_failure_status"], "FAIL")
        self.assertEqual(res["after_repair_status"], "PASS")

    def test_session_close_preserves_partial_blocked_dirty_and_safe_idempotent_cleanup(self) -> None:
        # Dirty uncommitted edit in repo must be preserved by session_close!
        (self.repo / "README.md").write_text("uncommitted partial work\n", encoding="utf-8")
        ev_dir = self.host_dir / "ev_close"
        ev_dir.mkdir()
        (ev_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (ev_dir / "checks_summary.json").write_text(
            json.dumps({
                "source_sha": self.base_sha,
                "candidate_sha256": "c" * 64,
                "diff_sha256": "d" * 64,
                "recorded_at": "2026-11-28T03:00:00Z",
                "results": [
                    {
                        "check_id": "verify-structure",
                        "domain": "foundation",
                        "status": "FAIL",
                        "exit_code": 1,
                        "receipt_path": "check_verify-structure.log",
                        "receipt_sha256": "e" * 64,
                        "finding": "Structure mismatch on test",
                    }
                ],
            }),
            encoding="utf-8",
        )
        (ev_dir / "check_verify-structure.log").write_text("Structure mismatch\n", encoding="utf-8")

        scratch_dir = self.host_dir / "scratch-run"
        obs.write_owner_marker(scratch_dir, issue=433, run_id="run-abc")
        (scratch_dir / "debug.log").write_text("temp scratch", encoding="utf-8")
        obs.write_owner_marker(ev_dir, issue=433, run_id="run-abc")
        tmp_file = ev_dir / "staging.tmp"
        tmp_file.write_text("temp", encoding="utf-8")

        closed = fs.session_close(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            next_action="Fix verify_structure.py and rerun check.py",
            blocker="verify-structure failed in foundation layer",
            evidence_dir=ev_dir,
            cleanup_paths=[scratch_dir, tmp_file],
            allowed_temp_roots=[self.host_dir],
            owner_run_id="run-abc",
            base_sha=self.base_sha,
        )
        self.assertEqual(closed["status"], "SESSION_CLOSED")
        self.assertEqual(closed["session_outcome"], "BLOCKED")
        self.assertTrue(closed["has_uncommitted_work"])
        self.assertIn("README.md", closed["dirty_paths"])
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "uncommitted partial work\n")
        self.assertFalse(scratch_dir.exists())
        self.assertFalse(tmp_file.exists())
        # Required review evidence MUST remain intact!
        self.assertTrue((ev_dir / "manifest.json").is_file())
        self.assertTrue((ev_dir / "checks_summary.json").is_file())
        self.assertTrue((ev_dir / "check_verify-structure.log").is_file())

        # Repeated cleanup is idempotent
        second = obs.cleanup_owned_artifacts(
            [scratch_dir, tmp_file],
            allowed_temp_roots=[self.host_dir],
            repo=self.repo,
            owner_issue=433,
            owner_run_id="run-abc",
        )
        self.assertEqual(second["removed"], [])
        self.assertEqual(len(second["already_absent"]), 2)

        # Fresh session_start restores exact blocker, dirty state, and failure diagnosis
        resumed = fs.session_start(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            issue_data=self.issue_data,
        )
        self.assertEqual(resumed["status"], "BLOCKED")
        self.assertTrue(resumed["has_uncommitted_work"])
        self.assertEqual(resumed["observability"]["latest_failure"]["check_id"], "verify-structure")

    def test_cleanup_negative_authorizations(self) -> None:
        ev_file = self.host_dir / "manifest.json"
        ev_file.write_text("{}", encoding="utf-8")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([ev_file], allowed_temp_roots=[self.host_dir], repo=self.repo)

        unowned_dir = self.host_dir / "unowned"
        unowned_dir.mkdir()
        (unowned_dir / "file.txt").write_text("keep", encoding="utf-8")
        unowned_sub_tmp = unowned_dir / "foreign.tmp"
        unowned_sub_tmp.write_text("keep tmp", encoding="utf-8")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([unowned_dir], allowed_temp_roots=[self.host_dir], repo=self.repo)
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([unowned_sub_tmp], allowed_temp_roots=[self.host_dir], repo=self.repo)
        self.assertTrue(unowned_sub_tmp.is_file())

        orphan_root_tmp = self.host_dir / "orphan.tmp"
        orphan_root_tmp.write_text("keep root tmp", encoding="utf-8")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([orphan_root_tmp], allowed_temp_roots=[self.host_dir], repo=self.repo)
        self.assertTrue(orphan_root_tmp.is_file())

        wrong_owner_dir = self.host_dir / "other-issue"
        obs.write_owner_marker(wrong_owner_dir, issue=999, run_id="other-run")
        wrong_owner_tmp = wrong_owner_dir / "other.tmp"
        wrong_owner_tmp.write_text("other issue tmp", encoding="utf-8")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([wrong_owner_dir], allowed_temp_roots=[self.host_dir], repo=self.repo, owner_issue=433)
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([wrong_owner_tmp], allowed_temp_roots=[self.host_dir], repo=self.repo, owner_issue=433)
        self.assertTrue(wrong_owner_tmp.is_file())

        owned_dir = self.host_dir / "owned-433"
        owned_marker = obs.write_owner_marker(owned_dir, issue=433, run_id="r433")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([owned_marker], allowed_temp_roots=[self.host_dir], repo=self.repo, owner_issue=433, owner_run_id="r433")
        self.assertTrue(owned_marker.is_file())

        sym_marker_dir = self.host_dir / "sym-marker-dir"
        sym_marker_dir.mkdir()
        (sym_marker_dir / obs.OWNER_MARKER_NAME).symlink_to(owned_marker)
        sym_marker_tmp = sym_marker_dir / "sneaky.tmp"
        sym_marker_tmp.write_text("keep", encoding="utf-8")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([sym_marker_tmp], allowed_temp_roots=[self.host_dir], repo=self.repo, owner_issue=433)
        self.assertTrue(sym_marker_tmp.is_file())

        sym_target = self.host_dir / "sym-dir"
        sym_target.symlink_to(unowned_dir)
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([sym_target], allowed_temp_roots=[self.host_dir], repo=self.repo)

        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([self.repo / "README.md"], allowed_temp_roots=[self.host_dir], repo=self.repo)

        outside_dir = self.root / "outside"
        outside_dir.mkdir()
        obs.write_owner_marker(outside_dir, issue=433, run_id="r1")
        with self.assertRaises(obs.CleanupError):
            obs.cleanup_owned_artifacts([outside_dir], allowed_temp_roots=[self.host_dir], repo=self.repo)

    def test_fresh_session_5_of_5_and_negative_drift(self) -> None:
        fs.session_checkpoint(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            next_action="Run check.py and open Draft PR",
            base_sha=self.base_sha,
        )
        bundle = obs.build_fresh_session_bundle(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            offline=True,
        )
        good_answers = {
            "system": "Custom LoRa P2P Event-Only MVP using CAD + CSMA/CA per ADR-0004 (docs/adr/0004-pure-cad-csma-ca-mac.md) and AGENTS.md.",
            "organization": "Monorepo with firmware/, backend-go/, clients/, contracts/, and scripts/agent_harness/.",
            "startup": "Run scripts/agent_harness/agent_context.py, scripts/harness_doctor.py, and feature_state.py session-start.",
            "verification": "Run scripts/agent_harness/check.py, quality_gates.py, and pr_review.py; RF/HIL remains NOT_VERIFIED without bench hardware.",
            "current_state_and_next_action": (
                f"Issue #433 on branch {self.branch} at {self.base_sha[:8]}: next action is Run check.py and open Draft PR."
            ),
        }
        pass_eval = obs.evaluate_fresh_session(answers=good_answers, expected_resume=bundle["resume_snapshot"])
        self.assertTrue(pass_eval["passed"], pass_eval)
        self.assertEqual(pass_eval["score"], 5)

        bad_answers = {**good_answers, "current_state_and_next_action": "Issue #999 on main, auto-merge now."}
        fail_eval = obs.evaluate_fresh_session(answers=bad_answers, expected_resume=bundle["resume_snapshot"])
        self.assertFalse(fail_eval["passed"])
        self.assertEqual(fail_eval["score"], 4)

    def test_interrupted_execution_revision_drift_and_cli_wrappers(self) -> None:
        # Interrupted PREPARING run -> RECOVERY_REQUIRED
        with Journal(self.journal_path) as j:
            j.plan(
                run_id="run-int-1",
                issue=433,
                source_sha=self.base_sha,
                issue_sha="a" * 64,
                branch=self.branch,
                worktree=self.repo,
                scope=("README.md",),
            )
            j.transition("run-int-1", expected="PLANNED", next_state="PREPARING")

        resumed = fs.session_start(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            issue_data=self.issue_data,
        )
        self.assertEqual(resumed["status"], "RECOVERY_REQUIRED")

        # Revision drift detection on checkpoint
        fs.session_checkpoint(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            next_action="Continue work",
            base_sha=self.base_sha,
        )
        (self.repo / "README.md").write_text("drifted content\n", encoding="utf-8")
        resumed_drift = fs.session_start(
            issue=433,
            repo=self.repo,
            state_db=self.journal_path,
            issue_data=self.issue_data,
        )
        self.assertTrue(resumed_drift["drift"]["checkpoint_revision_changed"])
        self.assertIn("candidate_sha256_changed", resumed_drift["drift"]["drift_reasons"])

        # p1/process.py timestamps
        rec = execute_checked(["true"], self.repo, timeout=5)
        self.assertTrue(rec.started_at.endswith("Z"))
        self.assertTrue(rec.ended_at.endswith("Z"))

        # pr_review.py --journal integration via fixture
        fixture = pathlib.Path(__file__).resolve().parents[2] / "tests/agent_harness/fixtures/pr_review/pr_clean_docs.json"
        with contextlib.redirect_stdout(io.StringIO()):
            rc = pr_rev.main(["--fixture", str(fixture), "--candidate-repo", str(pathlib.Path(__file__).resolve().parents[2]), "--journal", str(self.journal_path)])
        self.assertIn(rc, (0, 1, 2))
        pr_sigs = obs.query_signals(self.journal_path, signal_type="process", limit=20)
        self.assertTrue(any(s["category"] == "pr_review" for s in pr_sigs))

        # p1/cli.py close & signals CLI wrappers
        old_argv = sys.argv
        try:
            sys.argv = [
                "cli.py", "close",
                "--issue", "433",
                "--repo", str(self.repo),
                "--state", str(self.journal_path),
                "--next-action", "Review Draft PR",
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(p1_cli.main(), 0)
            sys.argv = [
                "cli.py", "signals",
                "--issue", "433",
                "--source", str(self.repo),
                "--state", str(self.journal_path),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(p1_cli.main(), 0)
        finally:
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
