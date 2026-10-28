import json
import tempfile
import unittest
from pathlib import Path

from app.ux_report import score_findings, write_ux_report


class UxReportTests(unittest.TestCase):
    def test_score_matches_the_severity_weights(self) -> None:
        findings = [
            {"severity": "S2"},
            {"severity": "S2"},
            {"severity": "S3"},
            {"severity": "S3"},
            {"severity": "S3"},
            {"severity": "S3"},
            {"severity": "S3"},
            {"severity": "O"},
        ]
        counts, score, verdict = score_findings(findings)
        self.assertEqual(counts, {"S0": 0, "S1": 0, "S2": 2, "S3": 5, "O": 1})
        self.assertEqual(score, 65)
        self.assertEqual(verdict, "ADVISORY-FAIL")

    def test_blocking_when_a_core_task_fails(self) -> None:
        _, score, verdict = score_findings([{"severity": "S1"}, {"severity": "S0"}])
        self.assertEqual(score, 35)
        self.assertEqual(verdict, "BLOCKING-FAIL")

    def test_html_report_has_cards_and_no_mock_images(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "2026-10-27_0836Z_demo"
            folder.mkdir()
            (folder / "ux-findings.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "UX-01",
                            "checkId": "CRUD-06",
                            "lens": "Clarity",
                            "severity": "S2",
                            "title": "No confirmation after save",
                            "evidence": "Clicked Save. The panel closed with no message.",
                            "solution": "Show a short confirmation.",
                            "implementationShadcn": "Sonner toast",
                            "fluentRationale": "Transient success uses a toast.",
                            "qaRefs": ["TC-1"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (folder / "ux-scorecard.json").write_text(
                json.dumps({"envNotes": ["Role inferred as owner."], "score": 1, "verdict": "PASS"}),
                encoding="utf-8",
            )
            report = write_ux_report(folder, "LEX-1")
            self.assertIsNotNone(report)
            html = report.read_text(encoding="utf-8")
            self.assertIn("finding-card severity-S2", html)
            self.assertIn("No confirmation after save", html)
            self.assertIn("Observed defect", html)
            self.assertIn("Design &amp; Remediation Plan", html)
            self.assertIn("UX Health Verdict", html)
            self.assertIn("Visual Score Gauge", html)
            self.assertIn('class="verdict verdict-advisory-fail"', html)
            self.assertNotIn("__", html)
            self.assertNotIn("finding-image-preview", html)
            self.assertNotIn("before-after", html)
            card = json.loads((folder / "ux-scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual(card["score"], 90)
            self.assertEqual(card["verdict"], "ADVISORY-FAIL")
            self.assertEqual(card["envNotes"], ["Role inferred as owner."])

    def test_observations_are_outside_the_defect_list(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "2026-10-27_1200Z_demo"
            folder.mkdir()
            (folder / "ux-findings.json").write_text(
                json.dumps(
                    [
                        {"id": "UX-D", "severity": "S2", "title": "Missing confirmation", "evidence": "No toast.", "solution": "Add one."},
                        {"id": "UX-O", "severity": "O", "title": "Label could be shorter", "evidence": "It works.", "solution": "Shorten it."},
                    ]
                ),
                encoding="utf-8",
            )
            report = write_ux_report(folder, "LEX-2")
            html = report.read_text(encoding="utf-8")
            findings = html.split('<div id="findings">', 1)[1].split("</div>", 1)[0]
            observations = html.split('<section class="observations-section">', 1)[1]
            self.assertIn("Missing confirmation", findings)
            self.assertNotIn("Label could be shorter", findings)
            self.assertIn("Label could be shorter", observations)
            self.assertIn("Observations and design suggestions", observations)

    def test_missing_files_does_not_invent_a_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(write_ux_report(Path(raw), "LEX-1"))


if __name__ == "__main__":
    unittest.main()
