"""Validate all tracked-style native AGY agent definitions and coordinator routing.

The allowlist is a conservative repository policy, not a vendor tool registry.
Extend it only with reviewed runtime smoke evidence for the intended AGY release.
"""
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".agents" / "agents"
SUPPORTED_AGY_TOOLS = {
    "run_command", "view_file", "write_file", "edit_file", "send_message",
    "manage_task", "search_web", "schedule", "generate_image", "invoke_subagent",
}


def validate_agent(content):
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing YAML frontmatter") from exc
    config = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(config, dict):
        raise ValueError("frontmatter must be a mapping")
    name = config.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("missing agent name")
    tools = config.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("tools must be a nonempty explicit list")
    if any(not isinstance(tool, str) or not tool for tool in tools):
        raise ValueError("invalid tool name")
    if len(tools) != len(set(tools)):
        raise ValueError("duplicate tool name")
    if "read_file" in tools:
        raise ValueError("read_file is a conflicting legacy alias; use view_file")
    unknown = set(tools) - SUPPORTED_AGY_TOOLS
    if unknown:
        raise ValueError("unreviewed native tool(s): " + ", ".join(sorted(unknown)))
    return config


class RepositoryAgentConfigTests(unittest.TestCase):
    def test_all_native_agent_definitions(self):
        paths = sorted(set(AGENTS.glob("*.md")) | set(AGENTS.rglob("agent.md")))
        self.assertTrue(paths, "no native agent definitions found")
        self.assertIn(AGENTS / "harness-coordinator.md", paths)
        names = set()
        for path in paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                config = validate_agent(path.read_text(encoding="utf-8"))
                self.assertNotIn(config["name"], names, "duplicate agent name")
                names.add(config["name"])

    def test_rejects_executor_regressions(self):
        invalid = [
            (["view_file", "read_file"], "conflicting legacy alias"),
            (["read_file"], "conflicting legacy alias"),
            (["view_file", "view_file"], "duplicate tool name"),
            (["run_command", "call_mcp_tool"], "unreviewed native tool"),
            (["run_command", "list_resources"], "unreviewed native tool"),
            (["run_command", "read_resource"], "unreviewed native tool"),
            (["run_command", "codegraph_explore"], "unreviewed native tool"),
            (["run_command", "unknown_tool"], "unreviewed native tool"),
            ([], "nonempty explicit list"),
            (["run_command", 123], "invalid tool name"),
        ]
        for tools, error in invalid:
            with self.subTest(tools=tools):
                fixture = "---\n" + yaml.safe_dump(
                    {"name": "fixture", "tools": tools}
                ) + "---\n"
                with self.assertRaisesRegex(ValueError, error):
                    validate_agent(fixture)

    def test_accepts_canonical_native_profile(self):
        fixture = "---\nname: fixture\ntools:\n  - run_command\n  - view_file\n---\n"
        self.assertEqual(validate_agent(fixture)["tools"], ["run_command", "view_file"])

    def test_agent_only_changes_trigger_harness_ci(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/ci-agent-harness.yml").read_text(encoding="utf-8")
        )
        # PyYAML YAML 1.1 may decode the key 'on' as boolean True.
        triggers = workflow.get("on", workflow.get(True))
        self.assertIn(".agents/agents/**", triggers["pull_request"]["paths"])
        commands = [
            step.get("run", "")
            for step in workflow["jobs"]["harness-unit"]["steps"]
        ]
        self.assertTrue(any("unittest discover -s tests/agent_harness" in cmd
                            for cmd in commands))


class HarnessCoordinatorConfigTests(unittest.TestCase):
    def setUp(self):
        self.coordinator_path = AGENTS / "harness-coordinator.md"
        self.content = self.coordinator_path.read_text(encoding="utf-8")
        self.config = validate_agent(self.content)

    def test_coordinator_file_exists(self):
        self.assertTrue(self.coordinator_path.is_file())

    def test_frontmatter_valid_yaml(self):
        self.assertEqual(self.config["name"], "harness-coordinator")
        self.assertIs(self.config["mainAgent"], True)
        self.assertIs(self.config["subagent"], False)

    def test_run_command_in_tools_allowlist(self):
        self.assertIn("run_command", self.config["tools"])
        self.assertIn("view_file", self.config["tools"])
        self.assertNotIn("read_file", self.config["tools"])

    def test_invoke_subagent_capability_required(self):
        self.assertIn("invoke_subagent", self.config["tools"])

    def test_preserves_required_instructions_and_pr_review_harness(self):
        for token in ("Chạy Issue #N", "Nghiệm thu PR #N",
                      "READ-ONLY PR REVIEW (`Nghiệm thu PR #N`):",
                      "scripts/agent_harness/pr_review.py", "READY_FOR_HUMAN_REVIEW"):
            self.assertIn(token, self.content)

    def test_pr_review_auditor_sequencing_instructions(self):
        for token in ("--export-auditor-context", "Fresh-Independent-Auditor",
                      "--auditor-report", "--evidence-dir", "invoke_subagent"):
            self.assertIn(token, self.content)


if __name__ == "__main__":
    unittest.main()
