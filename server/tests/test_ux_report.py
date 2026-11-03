import json
import tempfile
import unittest
from pathlib import Path

from app.ux_report import check_ux_report, score_findings, write_ux_report


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
        self.assertEqual(verdict, "PASS WITH ADVISORIES")

    def test_blocking_when_a_core_task_fails(self) -> None:
        _, score, verdict = score_findings([{"severity": "S1"}, {"severity": "S0"}])
        self.assertEqual(score, 35)
        self.assertEqual(verdict, "BLOCKED")

    def test_generator_renders_defects_observations_and_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "2026-10-27_0836Z_demo"
            folder.mkdir()
            (folder / "ux-findings.json").write_text(
                json.dumps({"findings": [
                    {"id": "UX-01", "checkId": "CRUD-06", "severity": "S2", "title": "No confirmation after save", "evidence": "x"},
                    {"id": "UX-02", "severity": "O", "title": "Label could be shorter", "evidence": "ok"},
                    {"id": "UX-03", "severity": "S2", "status": "Resolved", "title": "Focus returns now", "resolutionNote": "verified"},
                ]}),
                encoding="utf-8",
            )
            (folder / "ux-scorecard.json").write_text(json.dumps({"envNotes": ["Role inferred as owner."]}), encoding="utf-8")
            report = write_ux_report(folder, "LEX-1")
            self.assertIsNotNone(report)
            html = report.read_text(encoding="utf-8")
            for text in ("No confirmation after save", "Label could be shorter", "Focus returns now", "PASS WITH ADVISORIES", "LEX-1", "2026-10-27"):
                self.assertIn(text, html)
            self.assertNotIn("advisory-fail", html)
            card = json.loads((folder / "ux-scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual((card["score"], card["totalDeduction"], card["verdict"]), (90, 10, "PASS WITH ADVISORIES"))
            self.assertEqual(card["counts"]["S2"], 1)
            self.assertEqual(card["envNotes"], ["Role inferred as owner."])
            findings = json.loads((folder / "ux-findings.json").read_text(encoding="utf-8"))
            self.assertEqual([item["deductionPoints"] for item in findings], [10, 0, 0])

    def test_a_ticket_driven_report_passes_the_contract_check(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "2026-11-03_0928Z_demo"
            folder.mkdir()
            (folder / "context-pack.json").write_text(json.dumps({"ticket": {
                "key": "LEX-9", "summary": "Create a server",
                "description": "The New drawer creates a server record.",
                "acceptanceCriteria": "- Create stays disabled until a name is entered\n- Saving shows a confirmation",
            }}), encoding="utf-8")
            (folder / "ux-findings.json").write_text(json.dumps([{
                "id": "UX-01", "checkId": "CRUD-06", "severity": "S2", "title": "No confirmation after save",
                "scope": "In scope", "acceptanceCriteria": ["AC2"], "evidence": "Saved a server; no toast appeared.",
                "expectedVsActual": "Expected: a confirmation after save.\nActual: the drawer closes silently.",
                "solution": {"what": "Show a toast", "developer": "Call toast() after the mutation resolves", "design": "Fluent success toast"},
            }]), encoding="utf-8")
            (folder / "ux-scorecard.json").write_text(json.dumps({"journey": "Assets CRUD"}), encoding="utf-8")
            self.assertIsNotNone(write_ux_report(folder, "LEX-9"))
            card = json.loads((folder / "ux-scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual(card["journey"], "Assets CRUD")
            self.assertEqual(check_ux_report(folder), [])
            # A report without its required parts is reported line by line.
            (folder / "ux-report.html").write_text("<html><body>PASS BLOCKED</body></html>", encoding="utf-8")
            self.assertTrue(check_ux_report(folder))

    def test_a_resolved_finding_is_not_scored(self) -> None:
        counts, score, verdict = score_findings([{"severity": "S1", "status": "Resolved", "title": "Fixed"}])
        self.assertEqual((counts["S1"], counts["O"], score, verdict), (0, 1, 100, "PASS"))

    def test_a_stale_report_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "2026-10-29_1300Z_demo"
            folder.mkdir()
            (folder / "ux-findings.json").write_text(json.dumps([{"id": "UX-1", "severity": "S3", "title": "Tight spacing"}]), encoding="utf-8")
            (folder / "ux-report.html").write_text("<html><body>ADVISORY-FAIL</body></html>", encoding="utf-8")
            write_ux_report(folder, "LEX-4")
            html = (folder / "ux-report.html").read_text(encoding="utf-8")
            self.assertIn("PASS WITH ADVISORIES", html)
            self.assertNotIn("ADVISORY-FAIL", html)

    def test_duplicate_findings_score_once(self) -> None:
        counts, score, verdict = score_findings([
            {"checkId": "B3", "screen": "Notes", "severity": "S3", "title": "Tight spacing"},
            {"checkId": "B3", "screen": "Notes", "severity": "S3", "title": "Tight spacing"},
        ])
        self.assertEqual(counts["S3"], 1)
        self.assertEqual(score, 97)
        self.assertEqual(verdict, "PASS WITH ADVISORIES")

    def test_missing_files_does_not_invent_a_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(write_ux_report(Path(raw), "LEX-1"))

    def test_defects_wrapper_scores_like_findings_list(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "2026-10-29_1400Z_demo"
            folder.mkdir()
            (folder / "ux-findings.json").write_text(
                json.dumps(
                    {
                        "defects": [{"id": "UX-1", "severity": "S2", "title": "Focus lost", "evidence": "BODY active."}],
                        "observations": [{"id": "UX-O1", "severity": "O", "title": "Label length", "evidence": "OK."}],
                    }
                ),
                encoding="utf-8",
            )
            write_ux_report(folder, "LEX-5")
            card = json.loads((folder / "ux-scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual(card["score"], 90)
            self.assertEqual(card["verdict"], "PASS WITH ADVISORIES")
            self.assertEqual(card["counts"]["S2"], 1)


if __name__ == "__main__":
    unittest.main()
