import json
import tempfile
import unittest
from pathlib import Path

from app import bugs
from app.pipeline import patched_but_failing


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class BugMergeTest(unittest.TestCase):
    def test_triage_bug_takes_the_cited_findings_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _write(folder / "api-findings.json", {"findings": [{
                "id": "F1", "failure": "Cancel prompts after clear", "steps": ["Open New", "Clear expiry", "Cancel"],
                "expected": "No prompt", "actual": "Prompt shown", "rootCause": "dirty check",
            }]})
            (folder / "bug-evidence").mkdir()
            (folder / "bug-evidence" / "finding-F1.png").write_bytes(b"x")
            triage = {"failures": [], "bugs": [{"finding": "F1", "area": "Docs", "severity": "Low",
                                                 "affectedTests": ["TC-7"]}]}
            _write(folder / "triage-1.json", triage)
            filed = bugs.publish_bugs(folder, ticket="LEX-1", run_id="r", url="u", build="b", failed=1,
                                      triage=triage)
            self.assertTrue(filed)
            bug = json.loads((folder / "bugs.json").read_text())["bugs"][0]
            self.assertEqual(bug["expected"], "No prompt")
            self.assertEqual(bug["actual"], "Prompt shown")
            self.assertEqual(bug["steps"][0], "Open New")
            self.assertIn("bug-evidence/finding-F1.png", bug["screenshots"])
            self.assertEqual(bug["title"], "Docs: Cancel prompts after clear")
            self.assertEqual(bug["severity"], "Low")
            text = (folder / "bugs.md").read_text()
            self.assertIn("1. Open New", text)
            self.assertNotIn("The test failed", text)

    def test_patched_case_that_still_fails_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _write(folder / "triage-1.json", {"failures": [
                {"title": "Details tab", "class": "spec", "action": "patched"},
                {"title": "Other", "class": "spec", "action": "patched"}]})
            _write(folder / "playwright" / "results.json", {"suites": [{"title": "s", "specs": [
                {"title": "Details tab", "tests": [{"results": [{"status": "failed", "error": {"message": "x"}}],
                                                     "status": "unexpected"}]}]}]})
            lines = patched_but_failing(folder)
            self.assertEqual(len(lines), 1)
            self.assertIn("Details tab", lines[0])


if __name__ == "__main__":
    unittest.main()
