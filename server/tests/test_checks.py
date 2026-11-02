import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from app import checks, store, summary
from app.logbook import Logbook
from app.pipeline import _finish_ux, apply_verification
from app.runners import _key, _rerooted, is_transient

SPEC = """
test('TC-1: saves the name', async ({ page }) => {
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Saved')).toBeVisible()
  expect(await count(page)).toBe(3)
})

test('TC-2: shows the list', async ({ page }) => {
  await expect(page.locator('li')).toHaveCount(4)
})
"""


class ExpectationEditTest(unittest.TestCase):
    def test_a_locator_fix_is_not_an_expectation_change(self):
        after = SPEC.replace("getByText('Saved')", "getByRole('status')")
        self.assertEqual(checks.expectation_changes({"a.spec.ts": SPEC}, {"a.spec.ts": after}), [])

    def test_a_changed_expected_value_is_flagged(self):
        after = SPEC.replace(".toBe(3)", ".toBe(2)")
        changes = checks.expectation_changes({"a.spec.ts": SPEC}, {"a.spec.ts": after})
        self.assertEqual(len(changes), 1)
        self.assertIn("TC-1: saves the name", changes[0])
        self.assertIn(".toBe(3)", changes[0])
        self.assertIn(".toBe(2)", changes[0])

    def test_a_removed_test_is_a_gap_not_an_edit(self):
        after = SPEC.split("test('TC-2")[0]
        self.assertEqual(checks.expectation_changes({"a.spec.ts": SPEC}, {"a.spec.ts": after}), [])

    def test_a_dropped_assertion_is_flagged(self):
        after = SPEC.replace("  expect(await count(page)).toBe(3)\n", "")
        changes = checks.expectation_changes({"a.spec.ts": SPEC}, {"a.spec.ts": after})
        self.assertEqual(len(changes), 1)
        self.assertIn("nothing", changes[0])


class CoverageAndHypothesesTest(unittest.TestCase):
    def _folder(self, raw: str) -> Path:
        folder = Path(raw)
        pack = {"ticket": {"acceptanceCriteria": "## Outcome\n- picker searches the full catalog\n- empty state shows a message"}}
        (folder / "context-pack.json").write_text(json.dumps(pack))
        return folder

    def test_no_coverage_file_falls_back(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(checks.coverage_blockers(self._folder(raw), []))

    def test_each_criterion_is_mapped_and_its_tests_passed(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = self._folder(raw)
            (folder / "coverage.json").write_text(json.dumps({"criteria": [
                {"ac": "AC1", "na": "heading"},
                {"ac": "AC2", "tests": ["TC-LEX-1-001"]},
            ]}))
            issues = checks.coverage_blockers(folder, ["TC-LEX-1-001: finds rare icons"])
            self.assertEqual(len(issues), 1)
            self.assertIn("AC3 is not in coverage.json", issues[0])

    def test_a_listed_test_that_did_not_pass_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = self._folder(raw)
            (folder / "coverage.json").write_text(json.dumps({"criteria": [
                {"ac": "AC1", "na": "heading"},
                {"ac": "AC2", "tests": ["TC-LEX-1-001"]},
                {"ac": "AC3", "gap": "no empty catalog on UAT"},
            ]}))
            issues = checks.coverage_blockers(folder, [])
            self.assertTrue(any("AC2 has no passing test" in i for i in issues))
            self.assertTrue(any(i.startswith("gap: AC3") for i in issues))

    def test_risks_with_no_hypothesis_tried_block(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "feature-map.md").write_text("# Map\n## Risks\n1. alias search\n2. reset on close\n## Unknowns\n- x\n")
            line, blockers = checks.hypothesis_report(folder)
            self.assertIn("0 tried", line)
            self.assertIn("lists 2 risk(s)", blockers[0])
            (folder / "hypotheses.json").write_text(json.dumps({"hypotheses": [
                {"id": "H1", "outcome": "refuted"}, {"id": "H2", "outcome": "confirmed"},
            ]}))
            line, blockers = checks.hypothesis_report(folder)
            self.assertIn("2 tried", line)
            self.assertEqual(blockers, ["hypothesis H2 was confirmed but no finding or bug cites it"])


class SignalsTest(unittest.TestCase):
    def test_cdn_blocks_and_auth_are_noise(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "playwright").mkdir()
            rows = [
                {"kind": "response", "method": "GET", "status": 403, "path": "/v1/x", "test": "a"},
                {"kind": "console", "text": "Request blocked by CloudFront", "test": "a"},
                {"kind": "response", "method": "POST", "status": 500, "path": "/v1/assets/1234abcd-0000", "test": "b"},
                {"kind": "pageerror", "text": "TypeError: x is undefined", "test": "b"},
            ]
            (folder / "playwright" / "signals.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            data = checks.summarize_signals(folder)
            self.assertEqual(data["count"], 2)
            self.assertEqual(data["serverErrors"], 1)
            self.assertIn("POST 500 /v1/assets/:id", data["line"])


class RunnersHelpersTest(unittest.TestCase):
    def test_transient_errors(self):
        self.assertTrue(is_transient("Connection lost while reading the response: ECONNRESET"))
        self.assertTrue(is_transient("getaddrinfo ETIMEOUT bedrock-runtime.us-east-1.amazonaws.com"))
        self.assertTrue(is_transient("Session interrupted: inactivity"))
        self.assertFalse(is_transient("Model not found: us.anthropic.claude-x"))
        self.assertFalse(is_transient(""))

    def test_key_survives_the_rename_at_seal(self):
        self.assertEqual(_key(Path("2026-10-30_1222Z_06f4")), _key(Path("2026-10-30_1222Z_06f4_14-passed_0-failed_perfect")))

    def test_planned_spec_paths_are_rerooted_after_a_rename(self):
        with tempfile.TemporaryDirectory() as raw:
            run = Path(raw) / "2026-10-30_1222Z_06f4_0-passed_0-failed_halted"
            (run / "specs").mkdir(parents=True)
            (run / "specs" / "a.spec.ts").write_text("test('x', async () => {})")
            found = _rerooted(run, "runs/tickets/LEX-1/2026-10-30_1222Z_06f4/specs/a.spec.ts")
            self.assertTrue(found.endswith("2026-10-30_1222Z_06f4_0-passed_0-failed_halted/specs/a.spec.ts"))


class StoreIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("QA_RUNS_DIR")
        os.environ["QA_RUNS_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("QA_RUNS_DIR", None)
        else:
            os.environ["QA_RUNS_DIR"] = self.old
        self.tmp.cleanup()

    def test_a_damaged_index_is_read_from_the_backup(self):
        first = store.create_run(ticket="LEX-1", pr=None, sha=None)
        store.create_run(ticket="LEX-2", pr=None, sha=None)
        index = Path(self.tmp.name) / "index.json"
        index.write_text('{"runs": [')
        rows = store.list_runs()
        self.assertTrue(any(row["id"] == first["id"] for row in rows))

    def test_a_damaged_index_without_backup_is_never_read_as_empty(self):
        index = Path(self.tmp.name) / "index.json"
        index.write_text("{broken")
        with self.assertRaises(RuntimeError):
            store.list_runs()


class SummaryTest(unittest.TestCase):
    def test_the_summary_names_where_the_run_stopped(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            book = Logbook(folder)
            run = summary.get("run-1")
            run.begin("preflight")
            run.begin("explore + author")
            run.end("explore + author", "ok")
            run.begin("ui-ux audit", parallel=True)
            run.begin("playwright")
            run.end("ui-ux audit", "failed", "Session interrupted: inactivity")
            data = summary.write("run-1", folder, book, ticket="LEX-1", verdict="NEEDS_REVISION",
                                 status="needs_revision", counts={"passed": 3, "failed": 0},
                                 issues=["gap: x"], costs={"Heal": {"cost": 0.25}})
            self.assertEqual(data["stoppedAt"]["phase"], "ui-ux audit")
            log = (folder / "run.log").read_text()
            self.assertIn("── run summary", log)
            self.assertIn("stopped at: ui-ux audit (failed)  Session interrupted: inactivity", log)
            self.assertIn("cost: $0.25", log)
            self.assertTrue((folder / "summary.json").is_file())


class UxAndVerifyTest(unittest.TestCase):
    def test_an_audit_that_wrote_nothing_is_not_run_not_score_100(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            summary.get("run-ux").begin("ui-ux audit", parallel=True)
            issue = _finish_ux("run-ux", folder, "LEX-1", Logbook(folder),
                               {"code": 1, "started": time.time(), "error": "Session interrupted: inactivity"})
            card = json.loads((folder / "ux-scorecard.json").read_text())
            self.assertEqual(card["verdict"], "NOT RUN")
            self.assertIsNone(card["score"])
            self.assertIn("did not run to the end", issue)
            summary.drop("run-ux")

    def test_verification_confirms_or_drops_findings(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "api-findings.json").write_text(json.dumps({"findings": [
                {"id": "F1", "confidence": "suspected"}, {"id": "F2", "confidence": "suspected"},
            ]}))
            (folder / "verify.json").write_text(json.dumps({"results": [
                {"ref": "finding:F1", "reproduced": True, "notes": "twice"},
                {"ref": "finding:F2", "reproduced": False, "notes": "fine on retry"},
            ]}))
            self.assertEqual(apply_verification(folder), "1 confirmed, 1 not reproduced")
            data = json.loads((folder / "api-findings.json").read_text())["findings"]
            self.assertEqual(data[0]["confidence"], "confirmed")
            self.assertEqual(data[1]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()


class SessionRecoveryTest(unittest.TestCase):
    def test_a_rejected_session_is_signed_in_again_and_the_run_is_retried(self):
        from unittest import mock
        from app import runners
        book = mock.Mock()
        lines = {None: (0, "session refreshed  persona admin"), "support": (0, "session reused  persona support")}
        with mock.patch.object(runners, "ensure_session", side_effect=lambda persona=None, **_: lines[persona]), \
             mock.patch.object(runners, "personas_requested", return_value=["support"]):
            self.assertTrue(runners._revoked_sessions(["a.spec.ts"], book))
        book.row.assert_called_once()
        with mock.patch.object(runners, "ensure_session", return_value=(0, "session reused  persona admin")), \
             mock.patch.object(runners, "personas_requested", return_value=[]):
            self.assertFalse(runners._revoked_sessions(["a.spec.ts"], book))
