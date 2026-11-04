import tempfile
import unittest
from pathlib import Path

from app.pipeline import _restore_suite, _suite_files, _triage_notes, record_promotion


class PromotionTest(unittest.TestCase):
    def test_a_promotion_is_logged_with_files_cases_and_skips(self):
        with tempfile.TemporaryDirectory() as raw:
            log = Path(raw) / "changes.log"
            before = {"document editing/doceditspec.spec.ts": "a", "document editing/FEATURE.md": "rows"}
            after = {**before, "document editing/doceditspec-3.spec.ts": "new", "document editing/FEATURE.md": "rows+1"}
            record_promotion(
                "LEX-3800-run", "LEX-3800", before, after,
                {"cases": [{"id": "TC-DOC-014", "title": "A saved PowerShell block is highlighted"}],
                 "skipped": [{"title": "cobol stays plain", "reason": "same assertion as TC-DOC-015"}]},
                log_path=log,
            )
            text = log.read_text()
            self.assertIn("promote from LEX-3800", text)
            self.assertIn("added: e2e test cases/document editing/doceditspec-3.spec.ts", text)
            self.assertIn("changed: e2e test cases/document editing/FEATURE.md", text)
            self.assertIn("- added / TC-DOC-014: A saved PowerShell block is highlighted", text)
            self.assertIn("- skipped: cobol stays plain — same assertion as TC-DOC-015", text)

    def test_nothing_promoted_writes_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            log = Path(raw) / "changes.log"
            record_promotion("r", "T", {"a.ts": "x"}, {"a.ts": "x"}, {"cases": []}, log_path=log)
            self.assertFalse(log.exists())

    def test_a_reverted_promotion_is_logged_and_the_suite_comes_back(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "suite"
            (root / "search").mkdir(parents=True)
            (root / "search" / "search.spec.ts").write_text("original")
            (root / "search" / "FEATURE.md").write_text("rows")
            before = _suite_files(root)
            (root / "search" / "bad.spec.ts").write_text("broken import")
            (root / "search" / "FEATURE.md").write_text("rows + a row for a test that is gone")
            (root / "search" / "search.spec.ts").unlink()
            _restore_suite(before, root)
            self.assertEqual(_suite_files(root), before)
            log = Path(raw) / "changes.log"
            record_promotion("r", "T", before, before, {"cases": []}, reverted="a promoted spec does not load", log_path=log)
            self.assertIn("reverted, the suite is unchanged: a promoted spec does not load", log.read_text())

    def test_heal_notes_group_tests_that_share_a_reason(self):
        failures = [{"title": f"test {n}", "class": "bug", "action": "reported", "reason": "seeded row missing"} for n in range(5)]
        failures.append({"title": "other", "class": "spec", "action": "patched", "reason": "renamed locator"})
        notes = _triage_notes({"failures": failures})
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0], "bug / reported (5 tests): test 0; test 1; test 2; +2 more — seeded row missing")
        self.assertEqual(notes[1], "spec / patched: other — renamed locator")


if __name__ == "__main__":
    unittest.main()


class TrimChangesLogTest(unittest.TestCase):
    def test_keeps_header_and_newest_entries(self):
        from app.pipeline import _trim_changes_log

        with tempfile.TemporaryDirectory() as raw:
            log = Path(raw) / "changes.log"
            entries = [f"2026-11-0{i}T10:00:00Z  run-{i}  heal 1\n  files: x\n" + "  - note\n" * 20 for i in range(1, 9)]
            log.write_text("Header line one.\nHeader line two.\n\n" + "\n".join(entries) + "\n", encoding="utf-8")
            _trim_changes_log(log, keep=900)
            text = log.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("Header line one."))
            self.assertIn("run-8", text)
            self.assertNotIn("run-1", text)
            self.assertLess(len(text), 1200)
