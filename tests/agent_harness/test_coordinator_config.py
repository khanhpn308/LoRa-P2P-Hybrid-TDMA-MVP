"""Unit tests for AGY custom agent harness-coordinator configuration."""

import unittest
from pathlib import Path
import yaml

SUPPORTED_AGY_TOOLS = {
    "run_command",
    "read_file",
    "view_file",
    "write_file",
    "edit_file",
    "send_message",
    "manage_task",
    "search_web",
    "schedule",
    "generate_image",
    "call_mcp_tool",
    "list_resources",
    "read_resource",
    "ask_question",
    "invoke_subagent",
    "define_subagent",
    "manage_subagents",
    "read_url_content",
}


class HarnessCoordinatorConfigTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.coordinator_path = self.repo_root / ".agents" / "agents" / "harness-coordinator.md"

    def test_coordinator_file_exists(self):
        self.assertTrue(self.coordinator_path.is_file(), f"Missing {self.coordinator_path}")

    def test_frontmatter_valid_yaml(self):
        content = self.coordinator_path.read_text(encoding="utf-8")
        parts = content.split("---")
        self.assertGreaterEqual(len(parts), 3, "File must have YAML frontmatter enclosed in ---")
        frontmatter = parts[1]
        data = yaml.safe_load(frontmatter)
        self.assertIsInstance(data, dict, "Frontmatter must parse to a dict")
        self.assertEqual(data.get("name"), "harness-coordinator")
        self.assertTrue(data.get("mainAgent"), "harness-coordinator must have mainAgent: true")
        self.assertFalse(data.get("subagent", True), "harness-coordinator must have subagent: false")

    def test_run_command_in_tools_allowlist(self):
        content = self.coordinator_path.read_text(encoding="utf-8")
        parts = content.split("---")
        frontmatter = parts[1]
        data = yaml.safe_load(frontmatter)
        tools = data.get("tools")
        self.assertIsInstance(tools, list, "tools must be declared as a list in frontmatter")
        self.assertIn("run_command", tools, "run_command must be present in tools list")
        self.assertIn("invoke_subagent", tools, "invoke_subagent must be present in tools list")
        for tool in tools:
            self.assertIn(
                tool,
                SUPPORTED_AGY_TOOLS,
                f"Tool {tool} is not in the set of supported AGY native tools",
            )

    def test_invoke_subagent_capability_required(self):
        content = self.coordinator_path.read_text(encoding="utf-8")
        parts = content.split("---")
        frontmatter = parts[1]
        data = yaml.safe_load(frontmatter)
        tools = data.get("tools", [])
        self.assertIn(
            "invoke_subagent",
            tools,
            "harness-coordinator must explicitly declare invoke_subagent capability",
        )

    def test_preserves_required_instructions_and_pr_review_harness(self):
        content = self.coordinator_path.read_text(encoding="utf-8")
        self.assertIn("Chạy Issue #N", content)
        self.assertIn("Nghiệm thu PR #N", content)
        self.assertIn("READ-ONLY PR REVIEW (`Nghiệm thu PR #N`):", content)
        self.assertIn("scripts/agent_harness/pr_review.py", content)
        self.assertIn("READY_FOR_HUMAN_REVIEW", content)


if __name__ == "__main__":
    unittest.main()
