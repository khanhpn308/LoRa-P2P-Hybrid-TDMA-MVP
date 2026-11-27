"""Pure-Python tests for fail-closed path validation."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from scope import parse_allowed_paths, violations, assert_scoped


BODY = """## Title
x
### Target Directories (allowed paths)
- `firmware/components/`
- `docs/verification/report.md`

### Acceptance Criteria
- `contracts/`
"""


class ScopeTests(unittest.TestCase):
    def test_scope_whitelist(self):
        self.assertEqual(parse_allowed_paths(BODY),
                         ("firmware/components/", "docs/verification/report.md"))

    def test_denies_parent_and_wildcard(self):
        for p in ("../firmware/", "firmware/*", "/absolute", "./src"):
            with self.subTest(path=p):
                with self.assertRaises(ValueError):
                    parse_allowed_paths("## Target Directories (allowed paths)\n- `" + p + "`")

    def test_missing_scope_is_error(self):
        with self.assertRaises(ValueError):
            parse_allowed_paths("## Scope\n- `firmware/`")

    def test_detect_out_of_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            bad = violations(root, parse_allowed_paths(BODY),
                             ["firmware/components/a.c", "contracts/api/openapi.yaml"])
            self.assertEqual(bad, ["outside Issue scope: contracts/api/openapi.yaml"])

    def test_denies_escape_symlink(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as target:
            root = pathlib.Path(d)
            (root / "firmware").mkdir()
            (root / "firmware" / "components").symlink_to(target, target_is_directory=True)
            bad = violations(root, ("firmware/components/",), ["firmware/components/payload.c"])
            self.assertTrue(any("symlink escape" in p for p in bad))

    def test_allows_intro_prose_before_list_while_failing_closed(self):
        body_with_prose = (
            "## Target Directories (allowed paths)\n"
            "Only the following paths may change:\n"
            "- `docs/harness/phase-01/HARNESS_BASELINE_REPORT.md`\n"
            "- `docs/harness/phase-01/HARNESS_RTM.json`\n\n"
            "## Work packages\n"
            "- `contracts/`\n"
        )
        self.assertEqual(
            parse_allowed_paths(body_with_prose),
            ("docs/harness/phase-01/HARNESS_BASELINE_REPORT.md",
             "docs/harness/phase-01/HARNESS_RTM.json"),
        )
        for bad_body in (
            "## Target Directories (allowed paths)\nNo bullet list here.\n## Next\n- `firmware/`\n",
            "## Target Directories (allowed paths)\n- firmware/\n",
            "## Target Directories (allowed paths)\nIntro prose\n",
        ):
            with self.subTest(bad_body=bad_body[:40]), self.assertRaises(ValueError):
                parse_allowed_paths(bad_body)


if __name__ == "__main__":
    unittest.main()
