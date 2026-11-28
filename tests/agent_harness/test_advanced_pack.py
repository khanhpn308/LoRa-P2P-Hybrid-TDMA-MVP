"""Tests for P07 Advanced Pack integration, link/freshness checks, DB schema, and lifecycle."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
import advanced_pack as ap

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


class AdvancedPackRepoTests(unittest.TestCase):
    def test_repo_advanced_pack_verify_passes_all_surfaces_and_links(self):
        res = ap.verify_advanced_pack(REPO_ROOT)
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["failure_count"], 0)
        self.assertTrue(all(res["mapped_surfaces"].values()), res["mapped_surfaces"])
        db = res["db_schema_check"]
        self.assertEqual(db["status"], "PASS")
        self.assertEqual(db["migration_count"], 11)
        self.assertEqual(db["active_table_count"], 13)
        self.assertIn("000004", db["duplicate_numeric_prefixes"])
        self.assertEqual(len(db["duplicate_numeric_prefixes"]["000004"]), 3)

    def test_repo_db_schema_tracks_drops_and_runner_semantics(self):
        info = ap.inspect_migrations(REPO_ROOT)
        active_names = {t["table"]: t for t in info["active_tables"]}
        dropped_names = {d["table"] for d in info["dropped_tables"]}
        # 000009 drops the 4 TDMA schedule tables from 000004_schedule_storage
        for tdma_tbl in ("schedules", "schedule_slots", "active_gateway_schedules", "schedule_migration_transactions"):
            self.assertIn(tdma_tbl, dropped_names)
            self.assertNotIn(tdma_tbl, active_names)
        # 000008 drops last_seen_at from gateway_status and node_health
        self.assertFalse(any(c.startswith("last_seen_at ") for c in active_names["gateway_status"]["columns"]))
        self.assertFalse(any(c.startswith("last_seen_at ") for c in active_names["node_health"]["columns"]))
        # Runner checks from backend-go/Dockerfile
        self.assertTrue(info["runner"]["uses_advisory_lock"])
        self.assertTrue(info["runner"]["tracks_full_filename"])
        self.assertTrue(info["runner"]["sorts_lexicographically"])
        self.assertTrue(info["ops_guide_mentions_golang_migrate"])


class AdvancedPackNegativeAndFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = pathlib.Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        (self.repo / "backend-go" / "migrations").mkdir(parents=True)
        (self.repo / "backend-go" / "Dockerfile").write_text(
            "SELECT pg_advisory_lock(1);\n"
            "find /app/migrations -maxdepth 1 -type f -name '*.up.sql' | sort\n"
            "WHERE version = '${base}'\n"
            "VALUES ('${base}')\n"
            "ON_ERROR_STOP=1\n",
            encoding="utf-8",
        )
        (self.repo / "backend-go" / "migrations" / "000001_init.up.sql").write_text(
            "CREATE TABLE items (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL);\n",
            encoding="utf-8",
        )
        (self.repo / "docs" / "generated").mkdir(parents=True)
        (self.repo / "docs" / "harness").mkdir(parents=True)
        ap.generate_db_schema(self.repo, self.repo / "docs" / "generated" / "db-schema.md")

        # Minimal valid ADVANCED_PACK.md and QUALITY_SCORE.md
        markers = "\n".join(f"- {label}: [db-schema.md](../generated/db-schema.md)" for _, label in ap.REQUIRED_SPEC_SURFACES)
        (self.repo / "docs" / "harness" / "ADVANCED_PACK.md").write_text(
            f"# Advanced Pack\nP08 P09 SUPERSEDED NOT_VERIFIED ADR-0004\n{markers}\n",
            encoding="utf-8",
        )
        (self.repo / "docs" / "QUALITY_SCORE.md").write_text(
            "# Quality Score\n"
            "Scale: A B C D NOT_VERIFIED\n"
            "No score overrides a hard gate.\n"
            "## Product Domains\n## Architectural Layers\n## Benchmark\n## Simplification\n"
            "## Deferred Technical Debt\nGitHub Issues #424\n",
            encoding="utf-8",
        )

    def test_stale_or_hand_edited_db_schema_rejected(self):
        schema_path = self.repo / "docs" / "generated" / "db-schema.md"
        self.assertEqual(ap.check_db_schema_freshness(self.repo, schema_path)["status"], "PASS")
        self.assertEqual(ap.verify_advanced_pack(self.repo)["status"], "PASS")

        # Hand-edit without regenerating -> FAIL
        orig = schema_path.read_text(encoding="utf-8")
        schema_path.write_text(orig.replace("items", "tampered_items"), encoding="utf-8")
        res_tampered = ap.check_db_schema_freshness(self.repo, schema_path)
        self.assertEqual(res_tampered["status"], "FAIL")
        self.assertIn("hand-edited", res_tampered["reason"])

        # Restore, then add a new migration -> stale FAIL
        ap.generate_db_schema(self.repo, schema_path)
        (self.repo / "backend-go" / "migrations" / "000002_extra.up.sql").write_text(
            "CREATE TABLE extra (id INT PRIMARY KEY);\n",
            encoding="utf-8",
        )
        res_stale = ap.check_db_schema_freshness(self.repo, schema_path)
        self.assertEqual(res_stale["status"], "FAIL")
        self.assertIn("stale", res_stale["reason"])
        self.assertEqual(ap.verify_advanced_pack(self.repo)["status"], "FAIL")

    def test_shallow_checkout_reproducible_without_disabling_stale_check(self):
        schema_path = self.repo / "docs" / "generated" / "db-schema.md"
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Tester"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "t@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "migrations and schema"], check=True)
        (self.repo / "README.md").write_text("unrelated later commit\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "later commit"], check=True)

        shallow_repo = pathlib.Path(self.temp.name) / "shallow"
        subprocess.run(
            ["git", "clone", "--quiet", "--depth=1", f"file://{self.repo}", str(shallow_repo)],
            check=True,
        )
        shallow_info = ap.inspect_migrations(shallow_repo)
        self.assertEqual(shallow_info["migrations_source_commit"], "SHALLOW_CHECKOUT_NO_FULL_HISTORY")
        self.assertEqual(
            ap.check_db_schema_freshness(shallow_repo, shallow_repo / "docs" / "generated" / "db-schema.md")["status"],
            "PASS",
        )
        self.assertEqual(ap.verify_advanced_pack(shallow_repo)["status"], "PASS")

        # Stale content check MUST still fail on a shallow checkout
        (shallow_repo / "backend-go" / "migrations" / "000002_extra.up.sql").write_text(
            "CREATE TABLE extra (id INT PRIMARY KEY);\n",
            encoding="utf-8",
        )
        stale_shallow = ap.check_db_schema_freshness(shallow_repo, shallow_repo / "docs" / "generated" / "db-schema.md")
        self.assertEqual(stale_shallow["status"], "FAIL")
        self.assertIn("stale", stale_shallow["reason"])

    def test_broken_link_and_missing_surface_rejected(self):
        adv = self.repo / "docs" / "harness" / "ADVANCED_PACK.md"
        adv.write_text(adv.read_text(encoding="utf-8") + "\n[Missing](does-not-exist.md)\n", encoding="utf-8")
        res = ap.verify_advanced_pack(self.repo)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("broken link" in f for f in res["failures"]))

        # Remove required SPEC §5.2 marker
        adv.write_text("# Advanced Pack\nP08 P09 SUPERSEDED NOT_VERIFIED ADR-0004\n", encoding="utf-8")
        res_missing = ap.verify_advanced_pack(self.repo)
        self.assertEqual(res_missing["status"], "FAIL")
        self.assertTrue(any("missing SPEC §5.2 surface" in f for f in res_missing["failures"]))

    def test_symlink_schema_path_rejected(self):
        target = self.repo / "docs" / "QUALITY_SCORE.md"
        link = self.repo / "docs" / "generated" / "db-schema.md"
        link.unlink()
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            ap.check_db_schema_freshness(self.repo, link)

    def test_disposable_plan_lifecycle_and_quality_debt_update(self):
        plan = {"plan_id": "PLAN-P07-FIXTURE", "issue": 435, "state": "DRAFT", "history": []}
        plan = ap.transition_plan_lifecycle(plan, target_state="ACTIVE")
        with self.assertRaises(ValueError):
            ap.transition_plan_lifecycle(plan, target_state="COMPLETED", evidence_ref="")
        plan = ap.transition_plan_lifecycle(plan, target_state="COMPLETED", evidence_ref="checks_summary.json#sha256:abc")
        with self.assertRaises(ValueError):
            ap.transition_plan_lifecycle(plan, target_state="ARCHIVED", evidence_ref="checks_summary.json#sha256:abc")
        plan = ap.transition_plan_lifecycle(
            plan,
            target_state="ARCHIVED",
            evidence_ref="checks_summary.json#sha256:abc",
            approved_by="owner:khanhpn308",
        )
        self.assertEqual(plan["state"], "ARCHIVED")
        self.assertEqual([h["to"] for h in plan["history"]], ["ACTIVE", "COMPLETED", "ARCHIVED"])

        snapshot = {"domains": {"agent-harness": {"grade": "C"}}, "debt": {"424": {"status": "OPEN"}}}
        with self.assertRaises(ValueError):
            ap.record_quality_debt_update(
                snapshot,
                domain="agent-harness",
                new_grade="A",
                evidence_ref="checks_summary.json",
                revision="059fa45fc",
                hard_gate_passed=False,
            )
        updated = ap.record_quality_debt_update(
            snapshot,
            domain="agent-harness",
            new_grade="B",
            evidence_ref="advanced_pack.py#verify:PASS",
            revision="059fa45fc",
            debt_issue=424,
            debt_status="OPEN",
            hard_gate_passed=True,
        )
        self.assertEqual(updated["domains"]["agent-harness"]["grade"], "B")
        self.assertEqual(updated["debt"]["424"]["last_reviewed_revision"], "059fa45fc")


if __name__ == "__main__":
    unittest.main()
