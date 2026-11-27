"""Tests for OD-03 Unified Check Runner, Impact Matrix, and OD-07 Bench Guard."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
import check as check_mod
import feature_state as fs
from p1.state import Journal


def _git(repo: pathlib.Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return p.stdout.strip()


class CheckMatrixAndExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "feature/431-test")
        _git(self.repo, "config", "user.name", "Harness Test")
        _git(self.repo, "config", "user.email", "test@example.invalid")
        self._write(".gitignore", "__pycache__/\n*.pyc\n")
        self._write("AGENTS.md", "# Agents\nTest\n")
        self._write("README.md", "baseline\n")
        self._write("scripts/verify_structure.py", "print('PASS: structure ok')\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")

    def _write(self, rel: str, content: str) -> pathlib.Path:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_impact_matrix_omits_whole_product_builds_for_docs_only(self):
        docs_checks = [s.check_id for s in check_mod.plan_checks(["README.md"], profile="software")]
        self.assertEqual(docs_checks, ["verify-structure"])

        go_checks = [s.check_id for s in check_mod.plan_checks(["backend-go/internal/app/app.go"], profile="software")]
        self.assertIn("go-test", go_checks)
        self.assertIn("go-vet", go_checks)
        self.assertNotIn("firmware-gateway-build", go_checks)
        self.assertNotIn("web-unit", go_checks)

        fw_checks = [s.check_id for s in check_mod.plan_checks(["firmware/components/lora_mac/src/lora_mac.c"], profile="software")]
        self.assertIn("firmware-unit", fw_checks)
        self.assertIn("firmware-gateway-build", fw_checks)
        self.assertNotIn("go-test", fw_checks)

    def test_freeze_and_recompute_on_full_diff_plus_real_execution(self):
        frozen_path = self.root / "frozen_plan.json"
        plan = check_mod.freeze_checks(
            self.repo,
            allowed_paths=["README.md"],
            base_sha=self.base,
            profile="quick",
            out_path=frozen_path,
        )
        self.assertEqual([c["check_id"] for c in plan["checks"]], ["verify-structure"])

        # Edit README.md cleanly and execute via check.py
        self._write("README.md", "updated docs\n")
        ev_dir = self.root / "ev_docs"
        res = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="quick",
            evidence_dir=ev_dir,
            frozen_plan_path=frozen_path,
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["quality_gates"]["auto_check"], "AUTO_CHECK_PASS")
        manifest = json.loads((ev_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["command_receipts"]), 1)
        rec = manifest["command_receipts"][0]
        self.assertEqual(rec["diff_sha256"], res["diff_sha256"])
        self.assertEqual(
            hashlib.sha256((ev_dir / rec["receipt_path"]).read_bytes()).hexdigest(),
            rec["receipt_sha256"],
        )

        # Adding a contracts file after freezing docs must recompute and require contracts check
        self._write("contracts/mqtt/schemas/test.schema.json", "{}\n")
        res_expanded = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="quick",
            evidence_dir=self.root / "ev_expanded",
            frozen_plan_path=frozen_path,
        )
        ids = {r["check_id"] for r in res_expanded["results"]}
        self.assertIn("verify-structure", ids)
        self.assertIn("dependency-boundaries-contracts", ids)

    def test_failing_command_returns_nonzero_never_skipped(self):
        self._write("scripts/verify_structure.py", "import sys; print('FAIL: broken'); sys.exit(1)\n")
        ev_dir = self.root / "ev_fail"
        res = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="quick",
            evidence_dir=ev_dir,
        )
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["exit_code"], 1)
        self.assertEqual(res["results"][0]["status"], "FAIL")

    def test_missing_prerequisite_fails_nonzero_not_verified(self):
        self._write("clients/web-dashboard/package.json", json.dumps({"name": "web"}))
        self._write("clients/web-dashboard/src/types/api.ts", "export type T = string;\n")
        ev_dir = self.root / "ev_prereq"
        res = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="software",
            evidence_dir=ev_dir,
        )
        self.assertEqual(res["status"], "NOT_VERIFIED")
        self.assertEqual(res["exit_code"], 2)
        web_res = [r for r in res["results"] if r["check_id"] == "web-unit"]
        self.assertEqual(len(web_res), 1)
        self.assertEqual(web_res[0]["status"], "NOT_VERIFIED")

    def test_bench_profile_blocked_without_explicit_authorization_and_equipment(self):
        self._write("tests/hil/test_dummy.py", "import unittest\n")
        res_no_flag = check_mod.run_checks(self.repo, base_sha=self.base, profile="bench")
        self.assertEqual(res_no_flag["status"], "NOT_VERIFIED")
        self.assertEqual(res_no_flag["hil_rf"], "NOT_VERIFIED")
        self.assertEqual(res_no_flag["exit_code"], 2)

        auth_file = self.root / "bench_auth.json"
        auth_file.write_text(json.dumps({"authorized": True, "equipment_available": False}), encoding="utf-8")
        res_no_equip = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="bench",
            evidence_dir=self.root / "ev_bench",
            allow_bench=True,
            bench_auth=auth_file,
        )
        self.assertEqual(res_no_equip["status"], "NOT_VERIFIED")
        self.assertEqual(res_no_equip["exit_code"], 2)

    def test_tampered_or_in_repo_frozen_plan_rejected(self):
        in_repo_plan = self.repo / "frozen.json"
        with self.assertRaises(ValueError):
            check_mod.freeze_checks(self.repo, allowed_paths=["README.md"], base_sha=self.base, out_path=in_repo_plan)

        ext_plan = self.root / "ext_frozen.json"
        check_mod.freeze_checks(self.repo, allowed_paths=["README.md"], base_sha=self.base, out_path=ext_plan)
        tampered = json.loads(ext_plan.read_text(encoding="utf-8"))
        tampered["checks"] = []
        ext_plan.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaises(ValueError):
            check_mod.run_checks(self.repo, base_sha=self.base, profile="quick", frozen_plan_path=ext_plan)

    def test_check_runner_satisfies_multi_command_feature_state_verify_unit(self):
        self._write("README.md", "behavior path ok\n")
        snap = fs.compute_candidate_snapshot(self.repo, base_sha=self.base)
        unit = {
            "id": "U-01",
            "behavior": "Verify structure and dependency boundaries via check.py",
            "verification": {
                "criteria": ["Structure check and dependency check pass"],
                "commands": [
                    "python3 scripts/verify_structure.py",
                    "python3 scripts/agent_harness/dependency_checks.py --repo . --json",
                ],
            },
            "dependencies": [],
            "scope": ["README.md"],
            "state": "PENDING",
        }
        # Simulate harness change so dependency-boundaries and software security gates run
        self._write("scripts/agent_harness/dependency_checks.py", "import json; print(json.dumps({'status': 'PASS'}))\n")
        self._write("scripts/agent_harness/adapters/audit.schema.json", "{}\n")
        self._write("scripts/harness_doctor.py", "print('{\"ready\": true}')\n")
        self._write("tests/agent_harness/__init__.py", "")
        self._write(
            "tests/agent_harness/test_quality_gates.py",
            "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n",
        )
        self._write(
            "tests/agent_harness/test_standards_policy.py",
            "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n",
        )
        unit["scope"] = ["README.md", "scripts/agent_harness/", "tests/agent_harness/"]
        snap = fs.compute_candidate_snapshot(self.repo, base_sha=self.base)
        doc = fs.create_feature_doc(
            431,
            units=[unit],
            approved_scope=["README.md", "scripts/agent_harness/", "tests/agent_harness/"],
            base_sha=self.base,
            head_sha=snap["source_sha"],
            branch=snap["branch"],
            candidate_sha256=snap["candidate_sha256"],
        )
        doc = fs.activate_unit(doc, "U-01")
        ev_quick = self.root / "ev_quick"
        quick_res = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="quick",
            evidence_dir=ev_quick,
            verification_sha256=doc["units"][0]["verification"]["definition_sha256"],
            run_quality_gates=False,
        )
        self.assertEqual(quick_res["status"], "PASS", quick_res)
        quick_manifest = json.loads((ev_quick / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("SECURITY-CHECK", quick_manifest["checks"])

        ev_dir = self.root / "ev_multi"
        res = check_mod.run_checks(
            self.repo,
            base_sha=self.base,
            profile="software",
            evidence_dir=ev_dir,
            verification_sha256=doc["units"][0]["verification"]["definition_sha256"],
        )
        self.assertEqual(res["status"], "PASS", res)
        manifest = json.loads((ev_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("SECURITY-CHECK", manifest["checks"])
        self.assertEqual(manifest["checks"]["SECURITY-CHECK"]["observations"]["check_id"], "harness-security-gates")

        proof = fs.verify_host_gate_evidence(
            doc,
            "U-01",
            repo=self.repo,
            base_sha=self.base,
            evidence_dir=ev_dir,
        )
        passed = fs.verify_unit_passing(doc, "U-01", proof=proof)
        self.assertEqual(passed["units"][0]["state"], "PASSING")
        db = self.root / "host" / "state.sqlite"
        with Journal(db) as journal:
            journal.save_feature_snapshot(
                issue=431,
                expected_revision=None,
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor="coordinator",
            )
            journal.save_feature_snapshot(
                issue=431,
                expected_revision=doc["revision"],
                revision=passed["revision"],
                doc_json=json.dumps(passed, sort_keys=True),
                units=passed["units"],
                actor="host_verifier",
                host_proofs={"U-01": proof},
            )
            loaded = journal.get_feature_snapshot(431)
            self.assertEqual(loaded["doc"]["units"][0]["state"], "PASSING")


if __name__ == "__main__":
    unittest.main()
