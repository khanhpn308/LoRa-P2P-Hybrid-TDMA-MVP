"""Tests for H2-INS-06 / FBK-04 structural dependency boundary checks."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
import dependency_checks as dc

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


class DependencyBoundaryTests(unittest.TestCase):
    def test_real_repository_passes_all_domains(self):
        report = dc.evaluate_dependencies(REPO_ROOT)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["violation_count"], 0)
        self.assertEqual(report["domains"], ["firmware", "backend-go", "clients", "contracts"])

    def _mk_repo(self) -> pathlib.Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return pathlib.Path(tmp.name)

    def _write(self, root: pathlib.Path, rel: str, content: str) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def test_firmware_seeded_negative_boundaries_and_comment_safety(self):
        repo = self._mk_repo()
        # Shared component depending on app component + comment that must NOT false-positive.
        self._write(
            repo,
            "firmware/components/lora_mac/CMakeLists.txt",
            "idf_component_register(SRCS \"src/lora_mac.c\" INCLUDE_DIRS \"include\" REQUIRES gateway_wal)\n",
        )
        self._write(
            repo,
            "firmware/components/lora_mac/include/lora_mac.h",
            "/* #include \"gateway_app.h\" */\nint mac_init(void);\n",
        )
        self._write(
            repo,
            "firmware/components/lora_mac/src/lora_mac.c",
            "#include \"lora_mac.h\"\n#include \"gateway_wal.h\"\n",
        )
        self._write(
            repo,
            "firmware/gateway_master/components/gateway_wal/CMakeLists.txt",
            "idf_component_register(SRCS \"src/gateway_wal.c\" INCLUDE_DIRS \"include\" REQUIRES)\n",
        )
        self._write(
            repo,
            "firmware/gateway_master/components/gateway_wal/include/gateway_wal.h",
            "void wal_init(void);\n",
        )
        self._write(
            repo,
            "firmware/sensor_node/components/node_ui/CMakeLists.txt",
            "idf_component_register(SRCS \"src/node_ui.c\" INCLUDE_DIRS \"include\" REQUIRES gateway_wal)\n",
        )
        self._write(
            repo,
            "firmware/sensor_node/components/node_ui/src/node_ui.c",
            "#include \"lorawan_mac.h\"\n",
        )
        self._write(
            repo,
            "firmware/sensor_node/main/extra_subsystem.c",
            "void extra(void) {}\n",
        )

        report = dc.evaluate_dependencies(repo, domains=["firmware"])
        self.assertEqual(report["status"], "FAIL")
        rule_ids = {v["rule_id"] for v in report["violations"]}
        self.assertIn("DEP-FW-001", rule_ids)
        self.assertIn("DEP-FW-002", rule_ids)
        self.assertIn("DEP-FW-004", rule_ids)
        self.assertIn("DEP-FW-005", rule_ids)
        for v in report["violations"]:
            self.assertNotIn("gateway_app.h", v["source"])
            self.assertTrue(v["reason"])
            self.assertTrue(v["fix"])

    def test_firmware_cycle_detected(self):
        repo = self._mk_repo()
        self._write(repo, "firmware/components/comp_a/CMakeLists.txt", "idf_component_register(REQUIRES comp_b)\n")
        self._write(repo, "firmware/components/comp_b/CMakeLists.txt", "idf_component_register(REQUIRES comp_a)\n")
        report = dc.evaluate_dependencies(repo, domains=["firmware"])
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("DEP-FW-003", {v["rule_id"] for v in report["violations"]})

    def test_go_seeded_negative_boundaries_and_comment_safety(self):
        repo = self._mk_repo()
        self._write(
            repo,
            "backend-go/go.mod",
            "module example.com/lora\n\ngo 1.27.3\n\nrequire github.com/redis/go-redis/v9 v9.0.0\n",
        )
        self._write(
            repo,
            "backend-go/cmd/server/main.go",
            'package main\nimport "example.com/lora/backend-go/internal/storage"\nfunc main() {}\n',
        )
        self._write(
            repo,
            "backend-go/internal/domain/event.go",
            'package domain\n// import "example.com/lora/backend-go/internal/storage"\n'
            'import "example.com/lora/backend-go/internal/api"\nconst note = "internal/mqtt"\n',
        )
        self._write(
            repo,
            "backend-go/internal/api/handler.go",
            'package api\nimport "example.com/lora/backend-go/internal/domain"\n',
        )
        self._write(
            repo,
            "backend-go/internal/storage/repo.go",
            'package storage\nimport "example.com/lora/backend-go/cmd/server"\n',
        )

        # Normalize prefix for test module path
        self._write(
            repo,
            "backend-go/go.mod",
            "module example.com/lora/backend-go\n\ngo 1.27.3\n\nrequire github.com/redis/go-redis/v9 v9.0.0\n",
        )
        report = dc.evaluate_dependencies(repo, domains=["backend-go"])
        self.assertEqual(report["status"], "FAIL")
        rule_ids = {v["rule_id"] for v in report["violations"]}
        self.assertIn("DEP-GO-001", rule_ids)
        self.assertIn("DEP-GO-002", rule_ids)
        self.assertIn("DEP-GO-003", rule_ids)
        self.assertIn("DEP-GO-005", rule_ids)
        self.assertIn("DEP-GO-006", rule_ids)
        for v in report["violations"]:
            self.assertNotIn("internal/mqtt", v["source"])
            self.assertTrue(v["fix"])

    def test_client_seeded_negative_boundaries(self):
        repo = self._mk_repo()
        self._write(
            repo,
            "clients/web-dashboard/package.json",
            json.dumps({"name": "web", "dependencies": {"pg": "^8.0.0"}}),
        )
        self._write(
            repo,
            "clients/web-dashboard/src/types/api.ts",
            'import { fetchNodes } from "@/lib/api/nodes";\nexport type Node = { id: string };\n',
        )
        self._write(
            repo,
            "clients/web-dashboard/src/lib/api/nodes.ts",
            'import mqtt from "mqtt";\nimport { Shell } from "@/components/Shell";\nexport const fetchNodes = () => ({ mqtt, Shell });\n',
        )
        self._write(
            repo,
            "clients/web-dashboard/src/components/Shell.tsx",
            'export const Shell = () => null;\n',
        )
        report = dc.evaluate_dependencies(repo, domains=["clients"])
        self.assertEqual(report["status"], "FAIL")
        rule_ids = {v["rule_id"] for v in report["violations"]}
        self.assertEqual(rule_ids, {"DEP-CLI-001", "DEP-CLI-002"})

    def test_contracts_seeded_negative_boundaries(self):
        repo = self._mk_repo()
        self._write(
            repo,
            "contracts/api/openapi.yaml",
            "openapi: 3.0.3\npaths:\n  /bad:\n    get:\n      responses:\n        '200':\n"
            "          content:\n            application/json:\n              schema:\n"
            "                $ref: '#/components/schemas/DoesNotExist'\n",
        )
        self._write(
            repo,
            "contracts/mqtt/schemas/bad.schema.json",
            json.dumps({"$ref": "../../../backend-go/internal/domain/event.go"}),
        )
        self._write(repo, "contracts/api/broken.yaml", "a: [unclosed\n")
        self._write(repo, "contracts/api/empty.yaml", "")
        self._write(repo, "contracts/api/caller.yaml", "schema:\n  $ref: './broken.yaml#/components/x'\nempty_ref:\n  $ref: './empty.yaml#/components/y'\n")
        report = dc.evaluate_dependencies(repo, domains=["contracts"])
        self.assertEqual(report["status"], "FAIL")
        rule_ids = {v["rule_id"] for v in report["violations"]}
        self.assertEqual(rule_ids, {"DEP-CTR-001", "DEP-CTR-002"})
        self.assertTrue(any("failed to parse" in v["reason"] for v in report["violations"]))
        self.assertTrue(any("does not exist in ./empty.yaml" in v["reason"] for v in report["violations"]))

    def test_cli_returns_nonzero_on_violation(self):
        repo = self._mk_repo()
        self._write(repo, "contracts/mqtt/schemas/bad.schema.json", json.dumps({"$ref": "https://evil.invalid/a.json"}))
        with patch.object(sys, "argv", ["dependency_checks.py", "--repo", str(repo), "--domain", "contracts", "--json"]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dc.main()
        self.assertEqual(rc, 1)
        data = json.loads(out.getvalue())
        self.assertEqual(data["status"], "FAIL")
        self.assertEqual(data["violations"][0]["rule_id"], "DEP-CTR-002")


if __name__ == "__main__":
    unittest.main()
