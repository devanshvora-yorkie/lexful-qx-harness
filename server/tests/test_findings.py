import json
import tempfile
import unittest
from pathlib import Path

from app.bugs import publish_findings


class FindingsTest(unittest.TestCase):
    def test_findings_are_filed_with_confidence_and_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "api-findings.json").write_text(json.dumps({"findings": [
                {"area": "Auth", "failure": "preview answers 200 to viewer", "severity": "High",
                 "expected": "403 per PR 2040", "actual": "200", "evidence": ["api-probes.jsonl:4"],
                 "confidence": "confirmed"},
                {"area": "Auth", "failure": "limit ignored", "expected": "max 100", "actual": "57 rows",
                 "evidence": ["api-probes.jsonl:7"]},
                {"area": "Auth", "failure": "no evidence", "expected": "x", "actual": "y"},
            ]}))
            self.assertEqual(publish_findings(folder, ticket="LEX-1", run_id="r", url="u", build="b"), 2)
            filed = {b["title"]: b for b in json.loads((folder / "bugs.json").read_text())["bugs"]}
            self.assertEqual(filed["Auth: preview answers 200 to viewer"]["confidence"], "confirmed")
            self.assertEqual(filed["Auth: limit ignored"]["confidence"], "suspected")
            text = (folder / "bugs.md").read_text()
            self.assertIn("## Auth: preview answers 200 to viewer", text)
            self.assertNotIn("no evidence", text)
            # Most severe first.
            self.assertLess(text.index("preview answers"), text.index("limit ignored"))

    def test_a_finding_claimed_by_a_triage_bug_is_not_filed_twice(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "triage-1.json").write_text(json.dumps({"failures": [], "bugs": [{"finding": "F1", "area": "A", "failure": "x"}]}))
            (folder / "api-findings.json").write_text(json.dumps({"findings": [
                {"id": "F1", "area": "A", "failure": "x", "expected": "e", "actual": "a", "evidence": ["e"]}]}))
            self.assertEqual(publish_findings(folder, ticket="T", run_id="r", url="u", build="b"), 0)

    def test_no_file_files_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(publish_findings(Path(raw), ticket="T", run_id="r", url="u", build="b"), 0)


if __name__ == "__main__":
    unittest.main()
