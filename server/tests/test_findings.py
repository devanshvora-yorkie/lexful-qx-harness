import json
import tempfile
import unittest
from pathlib import Path

from app.bugs import is_setup_failure, publish_findings


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
            text = (folder / "bugs.md").read_text()
            self.assertIn("preview answers 200 to viewer", text)
            self.assertIn("[suspected] limit ignored", text)
            self.assertNotIn("no evidence", text)

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

    def test_environment_failures_are_not_product_bugs(self):
        self.assertTrue(is_setup_failure("CloudFront 403 ERROR Request blocked"))
        self.assertTrue(is_setup_failure("LEX-2328 fixture not configured"))
        self.assertFalse(is_setup_failure("expected 403 got 200"))


if __name__ == "__main__":
    unittest.main()
