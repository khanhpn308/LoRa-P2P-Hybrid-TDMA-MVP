"""Static AGY/GOCARS integration checks, not native runtime enforcement."""
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / ".agents/agents/gocars-refactor/agent.md"
STANDARD = ROOT / "docs/development/backend-go/GOCARS.md"
WORKFLOW = ROOT / "docs/development/backend-go/gocars-agy-workflow.md"


class GocarsAgentConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = AGENT.read_text(encoding="utf-8")
        cls.standard = STANDARD.read_text(encoding="utf-8")
        cls.root = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_native_agent_frontmatter(self):
        parts = self.agent.split("---", 2)
        self.assertEqual(parts[0], "")
        config = yaml.safe_load(parts[1])
        self.assertEqual(config["name"], "gocars-refactor")
        self.assertIs(config["mainAgent"], True)
        self.assertIs(config["subagent"], False)
        self.assertEqual(config["model"], "inherit")
        # Explicit native profile: do not treat generic MCP aliases or plugin
        # tools as static registry entries. Changes require runtime smoke evidence
        # with the intended AGY release before extending this list.
        expected = [
            "run_command", "view_file", "write_file", "edit_file",
            "manage_task", "invoke_subagent", "send_message",
        ]
        self.assertEqual(config["tools"], expected)
        self.assertEqual(len(config["tools"]), len(set(config["tools"])))

    def test_reject_unsupported_executor_tools(self):
        config = yaml.safe_load(self.agent.split("---", 2)[1])
        unsupported = {
            "call_mcp_tool", "list_resources", "read_resource",
            "read_file", "codegraph_explore", "define_subagent",
        }
        self.assertFalse(unsupported.intersection(config["tools"]))
        self.assertIn("view_file", config["tools"])
        self.assertIn("run_command", config["tools"])

    def test_runtime_mcp_is_not_startup_dependency(self):
        for token in (
            "AGY executor compatibility (1.5.7 incident)",
            "actually callable in this selected agent",
            "CodeGraph CLI via `run_command`",
            "never loosen CG-005",
            "BLOCKED_CODEGRAPH",
        ):
            self.assertIn(token, self.agent)
        self.assertIn("executor", self.workflow)
        self.assertIn("unknown component", self.workflow)
        self.assertIn("1.5.7", self.workflow)

    def test_rule_id_registries(self):
        ids = re.findall(r"(?m)^\| (GO-[A-Z]+-\d{3}) \| (?:MUST NOT|MUST|SHOULD|MAY) \|", self.standard)
        self.assertEqual(len(ids), 52)
        self.assertEqual(len(set(ids)), 52)
        self.assertIn("GO-BE-002", ids)
        graph_ids = re.findall(r"(?m)^\| (CG-\d{3}) \|", self.agent)
        self.assertEqual(graph_ids, [f"CG-{i:03d}" for i in range(1, 11)])

    def test_graph_required_and_bounded(self):
        for token in ("BLOCKED_CODEGRAPH", "codegraph_explore", "codegraph explore",
                      "CG-005", "CG-007", "CG-009", "CG-010", "raw_read_exceptions",
                      "TOKEN_SAVINGS_NOT_MEASURED"):
            self.assertIn(token, self.agent)
        self.assertIn("No source-by-source exploration", self.agent)
        self.assertIn("MUST NOT fall back to recursive grep/read loops", self.agent)
        self.assertIn("complete cumulative diff", self.agent)

    def test_activation_and_authority(self):
        for token in ("Refactor lại codebase này", "AUDIT_ONLY", "PLAN_ONLY",
                      "REFACTOR", "VERIFY", "agent_context.py", "quality_gates.py",
                      "scoped V2", "fresh independent Auditor"):
            self.assertIn(token, self.agent)
        self.assertIn("APPROVED_ON_OWNER_MERGE", self.standard)
        self.assertIn("Issue #359", self.standard)
        self.assertIn("Neither namespace is submitted as new Host catalog IDs", self.root)
        self.assertIn("CodeGraph discovery is mandatory", self.root)
        self.assertIn("superseding Hybrid TDMA", self.root)
        self.assertIn("does not perform a second full-codebase engineering compliance audit", self.standard)

    def test_workflow_and_scope(self):
        for token in ("/agents", "Refactor backend #N", "BLOCKED_CODEGRAPH",
                      "NOT_VERIFIED", "backend-go/", "GO-BE-002"):
            self.assertIn(token, self.workflow)
        self.assertIn("not blanket write authorization", self.root)
        self.assertIn("No source edits without existing Host G0", self.root)
        self.assertTrue((ROOT / ".agents/agents/harness-coordinator.md").is_file())


if __name__ == "__main__":
    unittest.main()
