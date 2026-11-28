"""Regression checks for project AGY agent tool allowlists.

The list is a deliberately small reviewed set of canonical native identifiers,
not a claim about every tool supported by every AGY release. Do not add
permission-action names or aliases that resolve to a second native tool.
"""
import unittest
from pathlib import Path
import yaml

# Google Antigravity custom agent docs and native tool reference:
# https://antigravity.google/docs/cli/subagents
# https://antigravity.google/docs/hooks?tab=ide
SUPPORTED_AGY_TOOLS = {
    "run_command",
    "view_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
    "invoke_subagent",
}

REQUIRED_WORKFLOW_TOOLS = {
    "run_command", "view_file", "write_to_file",
    "replace_file_content", "invoke_subagent",
}


def load_agent_frontmatter(content):
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("Missing opening agent frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("Missing closing agent frontmatter") from exc
    # The tracked project format uses exactly one top-level tools key.
    if sum(line.startswith("tools:") for line in lines[1:end]) != 1:
        raise ValueError("Expected one top-level tools declaration")
    data = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(data, dict):
        raise ValueError("Agent frontmatter must be a mapping")
    return data


def validate_tool_allowlist(data):
    tools = data.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("tools must be a nonempty explicit list")
    if any(not isinstance(tool, str) for tool in tools):
        raise ValueError("tool names must be strings")
    if len(tools) != len(set(tools)):
        raise ValueError("duplicate native tool identifier")
    unknown = set(tools) - SUPPORTED_AGY_TOOLS
    if unknown:
        raise ValueError("unsupported or alias tool name: " + ", ".join(sorted(unknown)))
    return set(tools)


class HarnessCoordinatorConfigTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.agent_dir = self.repo_root / ".agents" / "agents"
        self.coordinator_path = self.agent_dir / "harness-coordinator.md"

    def test_coordinator_file_exists(self):
        self.assertTrue(self.coordinator_path.is_file(), f"Missing {self.coordinator_path}")

    def test_frontmatter_valid_yaml(self):
        data = load_agent_frontmatter(self.coordinator_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "harness-coordinator")
        self.assertTrue(data.get("mainAgent"))
        self.assertFalse(data.get("subagent", True))

    def test_all_project_agents_use_unique_canonical_tools(self):
        paths = sorted(self.agent_dir.glob("*.md")) + sorted(self.agent_dir.glob("*/agent.md"))
        self.assertIn(self.coordinator_path, paths)
        self.assertIn(self.agent_dir / "c-structural-refactor.md", paths)
        self.assertIn(self.agent_dir / "gocars-refactor" / "agent.md", paths)
        names = set()
        for path in paths:
            with self.subTest(path=str(path.relative_to(self.repo_root))):
                data = load_agent_frontmatter(path.read_text(encoding="utf-8"))
                validate_tool_allowlist(data)
                name = data.get("name")
                self.assertIsInstance(name, str)
                self.assertTrue(name.strip())
                self.assertNotIn(name, names, "duplicate agent name")
                names.add(name)

    def test_all_workflow_agents_preserve_required_capabilities(self):
        agents = {
            "harness-coordinator": self.agent_dir / "harness-coordinator.md",
            "c-structural-refactor": self.agent_dir / "c-structural-refactor.md",
            "gocars-refactor": self.agent_dir / "gocars-refactor" / "agent.md",
        }
        for name, path in agents.items():
            with self.subTest(agent=name):
                data = load_agent_frontmatter(path.read_text(encoding="utf-8"))
                self.assertEqual(data.get("name"), name)
                self.assertIs(data.get("mainAgent"), True)
                self.assertIs(data.get("subagent"), False)
                self.assertTrue(REQUIRED_WORKFLOW_TOOLS <= validate_tool_allowlist(data))

    def test_rejects_legacy_aliases_including_reported_collision(self):
        for tools in (["read_file", "view_file"], ["read_file"],
                      ["view_file", "write_file"], ["view_file", "edit_file"]):
            with self.subTest(tools=tools):
                with self.assertRaisesRegex(ValueError, "unsupported or alias"):
                    validate_tool_allowlist({"tools": tools})

    def test_rejects_duplicate_canonical_name(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_tool_allowlist({"tools": ["view_file", "view_file"]})

    def test_rejects_unreviewed_or_implicit_tools(self):
        for tool in ("unreviewed_tool", "send_message", "schedule", "generate_image",
                     "manage_task", "call_mcp_tool", "list_resources",
                     "read_resource", "codegraph_explore", "define_subagent"):
            with self.subTest(tool=tool):
                with self.assertRaisesRegex(ValueError, "unsupported or alias"):
                    validate_tool_allowlist({"tools": ["view_file", tool]})

    def test_rejects_invalid_tool_lists(self):
        for tools in (None, [], "view_file", [12]):
            with self.subTest(tools=tools):
                with self.assertRaises(ValueError):
                    validate_tool_allowlist({"tools": tools})

    def test_rejects_duplicate_tools_declaration(self):
        content = "---\nname: test\ntools:\n  - view_file\ntools:\n  - run_command\n---\n"
        with self.assertRaisesRegex(ValueError, "one top-level tools"):
            load_agent_frontmatter(content)

    def test_preserves_required_instructions_and_pr_review_harness(self):
        content = self.coordinator_path.read_text(encoding="utf-8")
        for marker in ("Chạy Issue #N", "Nghiệm thu PR #N",
                       "READ-ONLY PR REVIEW (`Nghiệm thu PR #N`):",
                       "scripts/agent_harness/pr_review.py", "READY_FOR_HUMAN_REVIEW"):
            self.assertIn(marker, content)

    def test_pr_review_auditor_sequencing_instructions(self):
        content = self.coordinator_path.read_text(encoding="utf-8")
        for marker in ("--export-auditor-context", "Fresh-Independent-Auditor",
                       "--auditor-report", "--evidence-dir", "invoke_subagent"):
            self.assertIn(marker, content)

    def test_agent_only_changes_trigger_harness_ci(self):
        workflow = yaml.safe_load(
            (self.repo_root / ".github/workflows/ci-agent-harness.yml").read_text(encoding="utf-8")
        )
        triggers = workflow.get("on", workflow.get(True))
        self.assertIn(".agents/**", triggers["pull_request"]["paths"])
        commands = [step.get("run", "") for step in workflow["jobs"]["harness-unit"]["steps"]]
        self.assertTrue(any("unittest discover -s tests/agent_harness" in cmd for cmd in commands))

    def test_ccars_graph_first_policy_preserved(self):
        content = (self.agent_dir / "c-structural-refactor.md").read_text(encoding="utf-8")
        for marker in ("CodeGraph is REQUIRED", "BLOCKED_CODEGRAPH", "PLAN_ONLY",
                       "codegraph_explore", "No bulk-read fallback"):
            self.assertIn(marker, content)

    def test_active_instruction_and_routing_links_exist(self):
        import re

        link_re = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
        active_docs = (
            "AGENTS.md",
            ".agents/agents/harness-coordinator.md",
            "docs/adr/README.md",
            "docs/hardware/sx1276/README.md",
            "docs/development/coding-standards.md",
            "docs/development/harness-fast-lane.md",
            "docs/development/agy-native-coordinator-sop.md",
            "docs/development/AI_TASK_START_PROTOCOL.md",
        )
        for rel in active_docs:
            doc_path = self.repo_root / rel
            text = doc_path.read_text(encoding="utf-8")
            for target in link_re.findall(text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (doc_path.parent / target).resolve()
                self.assertTrue(
                    resolved.exists(),
                    f"Broken link in {rel}: {target} -> {resolved}",
                )

    def test_coordinator_and_auditor_use_mac_v2_not_tdma_timing(self):
        coord = self.coordinator_path.read_text(encoding="utf-8")
        self.assertNotIn("TDMA timing PASS", coord)
        auditor = (self.repo_root / ".agent-harness" / "auditor.md").read_text(encoding="utf-8")
        self.assertIn("ADR-0004", auditor)
        self.assertNotIn("backend-controlled schedule", auditor)

    def test_p04_session_continuity_documented_and_schema_valid(self):
        import json
        coord = self.coordinator_path.read_text(encoding="utf-8")
        fast_lane = (self.repo_root / "docs" / "development" / "harness-fast-lane.md").read_text(encoding="utf-8")
        for marker in ("feature_state.py session-start", "feature_state.py checkpoint", "WIP=1"):
            self.assertIn(marker, coord)
        for marker in ("feature_state.py session-start", "feature_state.py checkpoint", "WIP=1"):
            self.assertIn(marker, fast_lane)
        schema_path = self.repo_root / "docs" / "harness" / "features" / "schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")

    def test_p07_advanced_pack_routing_and_links_valid(self):
        coord = self.coordinator_path.read_text(encoding="utf-8")
        fast_lane = (self.repo_root / "docs" / "development" / "harness-fast-lane.md").read_text(encoding="utf-8")
        qg = (self.repo_root / "docs" / "development" / "harness-quality-gates.md").read_text(encoding="utf-8")
        pr = (self.repo_root / "docs" / "development" / "harness-pr-review.md").read_text(encoding="utf-8")
        self.assertIn("advanced_pack.py verify", coord)
        self.assertIn("QUALITY_SCORE.md", fast_lane)
        self.assertIn("ADVANCED_PACK.md", fast_lane)
        self.assertIn("advanced-pack-freshness", qg)
        self.assertIn("QUALITY_SCORE.md", pr)


if __name__ == "__main__":
    unittest.main()
