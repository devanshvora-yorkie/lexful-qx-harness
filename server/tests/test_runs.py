import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from app.logbook import (
    Logbook,
    echo_run,
    format_event,
    plain_error,
    session_id_from_text,
)
from app import runners
from app.runners import _preflight_row, _session_expired
from app.main import LookupBody, health, internal_lookup, persona_client_allowed, run_phase1, run_ticket
from app.bugs import collect_bugs, publish_bugs, record, render_bugs
from app.coverage import load_cases, write_coverage_index
from app.pipeline import (
    PHASE_FILES,
    _lead_prompt,
    failed_tests,
    merge_test_outcomes,
    outcome_counts,
    test_outcomes_from_report,
    spec_was_patched,
    startup_order,
    record_suite_edits,
    suite_files_changed,
    suspicious_patches,
    heal_stopped_on_bugs,
    signoff_blockers,
    verdict_for,
)
from app.runners import checked_in_specs, common_test_dir, personas_requested, planned_specs
from app.store import (
    create_run,
    find_active_phase1,
    find_active_sha,
    get_run,
    list_runs,
    record_outcome,
    recover_runs,
    relocate_legacy_runs,
    update_run,
)


class LogbookTest(unittest.TestCase):
    def test_the_ux_audit_writes_its_own_rows_into_run_log(self):
        said = {"type": "text", "part": {"text": "Checking the create drawer."}}
        self.assertTrue(format_event(said).startswith("qa "))
        self.assertTrue(format_event(said, "ux-audit").startswith("ux-audit "))
        with tempfile.TemporaryDirectory() as raw:
            book = Logbook(Path(raw), role="ux-audit")
            book.event(json.dumps(said))
            text = (Path(raw) / "run.log").read_text(encoding="utf-8")
        self.assertIn("ux-audit", text)
        self.assertIn("Checking the create drawer.", text)

    def test_tool_and_error_lines(self):
        self.assertIsNone(format_event({"type": "step_start"}))
        shell = format_event({
            "type": "tool_use",
            "part": {"tool": "shell", "state": {"status": "completed", "input": {"command": "ls explore"}}},
        })
        self.assertIn("qa", shell)
        self.assertIn("shell", shell)
        self.assertIn("ls explore", shell)
        self.assertIn("ses", format_event({"type": "error", "error": {"message": "Expected a string starting with ses"}}))

    def test_plain_error_names_the_missing_session(self):
        line = plain_error("\x1b[91m\x1b[1mError: \x1b[0mSession not found")
        self.assertIn("Session not found", line)
        self.assertNotIn("\x1b", line)
        self.assertIsNone(plain_error("ordinary progress"))
        self.assertEqual(
            session_id_from_text('{"type":"step_start","sessionID":"ses_abcDEF1234567890"}'),
            "ses_abcDEF1234567890",
        )
        self.assertEqual(session_id_from_text("no session here"), "")
        check = _preflight_row("PASS  npm packages: @playwright/test and @playwright/cli are installed")
        self.assertIn("preflight", check)
        self.assertIn("pass", check)
        self.assertIn("npm packages", check)
        self.assertIn("installed", check)
        self.assertTrue(_session_expired("Error: Stytch session expired for persona admin"))
        self.assertTrue(_session_expired("Cookies saved, but the app landed on login"))
        self.assertFalse(_session_expired("locator timeout waiting for heading"))

    def test_appends_a_readable_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = Logbook(Path(tmp))
            book.row("server", "preflight", "ok")
            book.event('{"type":"step_finish","part":{"reason":"tool-calls","cost":0.02,"tokens":{"input":4,"output":10}}}')
            text = (Path(tmp) / "run.log").read_text(encoding="utf-8")
            self.assertIn("preflight", text)
            self.assertIn("$0.0200", text)
            self.assertIn("in 4 out 10", text)

    def test_e2e_lines_are_printed_on_the_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            echo_run(folder)
            book = Logbook(folder)
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                book.phase("E2E User Journey TCs")
                book.row("playwright", "test", "1 passed")
            text = printed.getvalue()
            self.assertIn("E2E User Journey TCs", text)
            self.assertIn("1 passed", text)
            self.assertIn("E2E User Journey TCs", (folder / "run.log").read_text(encoding="utf-8"))


class VerdictTest(unittest.TestCase):
    def test_matrix(self):
        self.assertEqual(verdict_for({"passed": 0, "failed": 0}, preflight_ok=False, produced_specs=False), "HALTED")
        self.assertEqual(verdict_for({"passed": 0, "failed": 0}, preflight_ok=True, produced_specs=False), "HALTED")
        self.assertEqual(verdict_for({"passed": 4, "failed": 0, "skipped": 0}, preflight_ok=True, produced_specs=True), "PERFECT")
        self.assertEqual(verdict_for({"passed": 3, "failed": 1}, preflight_ok=True, produced_specs=True), "NEEDS_REVISION")
        self.assertEqual(verdict_for({"passed": 4, "failed": 0, "skipped": 2}, preflight_ok=True, produced_specs=True), "NEEDS_REVISION")

    def test_a_required_gap_blocks_signoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "context-pack.json").write_text(json.dumps({
                "ticket": {"acceptanceCriteria": "* inline images stay protected after save\n* exact file-ID matching\n"},
            }), encoding="utf-8")
            (folder / "coverage.json").write_text(json.dumps({"criteria": [
                {"ac": "AC1", "tests": ["TC-LEX-1-001"]},
                {"ac": "AC2", "gap": "needs a second file with the same id"},
            ]}), encoding="utf-8")
            (folder / "playwright").mkdir()
            (folder / "playwright" / "test-outcomes.json").write_text(json.dumps([
                {"file": "a.spec.ts", "title": "TC-LEX-1-001: a saved inline image stays protected", "status": "passed", "tags": []},
            ]), encoding="utf-8")
            (folder / "ux-scorecard.json").write_text(json.dumps({
                "envNotes": ["E2E Demo holds 12 leftover fixtures from this run."],
            }), encoding="utf-8")
            issues = signoff_blockers(folder)
            self.assertTrue(any(item.startswith("gap: AC2") for item in issues))
            self.assertFalse(any("AC1" in item for item in issues))
            self.assertTrue(any(item.startswith("leftover fixtures:") for item in issues))

    def test_product_bugs_stop_the_heal_loop(self):
        self.assertTrue(heal_stopped_on_bugs({"failures": [{"class": "bug"}]}))
        self.assertFalse(heal_stopped_on_bugs({"failures": [{"class": "gap"}, {"class": "bug"}]}))
        self.assertFalse(heal_stopped_on_bugs({"failures": []}))


class Phase1Test(unittest.TestCase):
    def test_queue_puts_the_checked_in_suite_first(self):
        waiting = [
            {"id": "LEX-1-a", "kind": "ticket"},
            {"id": "regression-old", "kind": "phase1"},
        ]
        self.assertEqual(
            startup_order(waiting, "regression-new"),
            ["regression-new", "regression-old", "LEX-1-a"],
        )
        self.assertEqual(startup_order(waiting, "regression-old"), ["regression-old", "LEX-1-a"])

    def test_failure_class_and_suite_path(self):
        report = {
            "suites": [{
                "file": "e2e test cases/search/search.spec.ts",
                "specs": [
                    {"title": "renamed button", "ok": False, "tests": [{"status": "unexpected", "results": [{"status": "failed", "error": {"message": "waiting for getByRole('button', { name: 'Search' })"}}]}]},
                    {"title": "passes", "ok": True, "tests": []},
                ],
                "suites": [],
            }],
        }
        found = failed_tests(report)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["title"], "renamed button")
        self.assertTrue(found[0]["error"].startswith("waiting for getByRole"))
        self.assertTrue(spec_was_patched({"failures": [{"class": "spec", "action": "patched"}]}))
        self.assertTrue(spec_was_patched({"failures": [{"classification": "spec", "action": "patched"}]}))
        self.assertFalse(spec_was_patched({"failures": [{"class": "bug", "action": "reported"}]}))
        self.assertEqual(
            suspicious_patches({"failures": [{"class": "bug", "action": "patched", "title": "save failed"}]}),
            ["healer edited a bug failure: save failed"],
        )
        self.assertEqual(
            suite_files_changed((("a.ts", 1),), (("a.ts", 1), ("b.ts", 2))),
            ["b.ts"],
        )
        self.assertEqual(suite_files_changed((("a.ts", 1),), (("a.ts", 1),)), [])
        specs = checked_in_specs()
        self.assertGreaterEqual(len(specs), 3)
        self.assertTrue(all(item.startswith("e2e test cases/") for item in specs))
        directory = common_test_dir([
            "e2e test cases/asset crud/assets-crud.spec.ts",
            "e2e test cases/document editing/doceditspec.spec.ts",
            "e2e test cases/search/search.spec.ts",
        ])
        self.assertTrue(str(directory).endswith("e2e test cases"))

    def test_suite_edit_log_records_a_locator_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.log"
            record_suite_edits(
                "regression-1",
                1,
                {"asset crud/servers-listing-pom.ts": "getByText(/0 selected/)\n"},
                {"asset crud/servers-listing-pom.ts": "selectionCountText()\n"},
                {"failures": [{"class": "spec", "action": "patched", "title": "clear selection", "reason": "0selected"}]},
                log_path=path,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("e2e test cases/asset crud/servers-listing-pom.ts", text)
            self.assertIn("spec / patched: clear selection — 0selected", text)
            self.assertIn("-getByText(/0 selected/)", text)
            self.assertIn("+selectionCountText()", text)
            record_suite_edits(
                "regression-2",
                1,
                {"asset crud/servers-listing-pom.ts": "selectionCountText()\n"},
                {"asset crud/servers-listing-pom.ts": "selectionCountText()\n"},
                {"failures": [{"class": "bug", "action": "reported", "title": "archive count"}]},
                log_path=path,
            )
            again = path.read_text(encoding="utf-8")
            self.assertEqual(again.count("+selectionCountText()"), 1)
            self.assertIn("regression-2", again)
            self.assertIn("no file changes", again)
            self.assertIn("bug / reported: archive count", again)


class StoreTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / "runs"
        root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        os.environ["QA_RUNS_DIR"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        created = create_run(ticket="LEX-3371", pr=1418, sha="abc123")
        self.assertEqual(created["status"], "accepted")
        self.assertIsNone(created["opencodeSession"])
        self.assertTrue(created["folder"].startswith("tickets/LEX-3371/"))
        folder = Path(self.tmp.name) / created["folder"]
        self.assertTrue((folder / "manifest.json").is_file())
        self.assertFalse((folder / "contents.txt").is_file())
        update_run(created["id"], status="preflight")
        again = get_run(created["id"])
        self.assertIsNotNone(again)
        self.assertEqual(again["status"], "preflight")
        self.assertEqual(list_runs("LEX-3371")[0]["id"], created["id"])
        self.assertEqual(find_active_sha("abc123")["id"], created["id"])
        update_run(created["id"], status="needs_revision")
        self.assertIsNone(find_active_sha("abc123"))
        update_run(created["id"], status="failed")
        self.assertIsNone(find_active_sha("abc123"))

    def test_recovery_and_spec_discovery(self):
        created = create_run(ticket="LEX-3400", pr=None, sha=None)
        run = Path(self.tmp.name) / created["folder"]
        spec = run / "specs" / "added.spec.ts"
        spec.write_text("import { test } from '@playwright/test'\ntest('added', async () => {})\n")
        walk = run / "explore" / "flow.spec.ts"
        walk.parent.mkdir(parents=True, exist_ok=True)
        walk.write_text("test('walked step', async () => {})\n")
        (run / "planned-specs.json").write_text(
            json.dumps({"test_files": [str(walk.relative_to(Path(self.tmp.name)))]}),
            encoding="utf-8",
        )
        found = planned_specs(run, 0)
        self.assertTrue(any(item.endswith("added.spec.ts") for item in found))
        self.assertFalse(any("explore" in item for item in found))
        update_run(created["id"], status="agent")
        waiting = create_run(ticket="LEX-3401", pr=None, sha=None)
        update_run(waiting["id"], status="queued")
        requeued = recover_runs()
        self.assertIn(waiting["id"], requeued)
        failed = get_run(created["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("restarted", failed["error"])
        report = Path(self.tmp.name) / failed["folder"] / "linear-report.md"
        self.assertIn("restarted", report.read_text(encoding="utf-8"))
        self.assertFalse((report.parent / "report.md").exists())
        self.assertTrue((report.parent / "qa-result.json").is_file())

    def test_a_run_records_what_triggered_it(self):
        self.assertEqual(create_run(ticket="LEX-3500", pr=None, sha=None)["trigger"], "ticket")
        self.assertEqual(create_run(ticket=None, pr=12, sha=None)["trigger"], "pr")
        self.assertEqual(create_run(ticket=None, pr=None, sha="abc", trigger="uat-deploy")["trigger"], "uat-deploy")
        self.assertEqual(create_run(ticket=None, pr=None, sha=None, kind="phase1")["trigger"], "e2e")

    def test_a_pr_or_deploy_run_starts_under_its_ticket_and_never_moves(self):
        from app import pipeline
        with mock.patch.object(runners, "resolve_trigger", return_value={"ticket": "LEX-3642", "pr": 2245}):
            from_pr = pipeline.create_triggered_run(ticket=None, pr=2245, sha=None, trigger="pr")
        self.assertTrue(from_pr["folder"].startswith("tickets/LEX-3642/"))
        self.assertEqual((from_pr["ticket"], from_pr["pr"]), ("LEX-3642", 2245))
        with mock.patch.object(runners, "resolve_trigger", return_value={"ticket": "LEX-3509", "pr": 2263}):
            from_deploy = pipeline.create_triggered_run(ticket=None, pr=None, sha="f9251b0ec12ba8bd", trigger="uat-deploy")
        self.assertTrue(from_deploy["folder"].startswith("tickets/LEX-3509/"))
        self.assertEqual(from_deploy["pr"], 2263)
        # GitHub could not be read: the run stays under pull-requests/ or deploys/ for good.
        with mock.patch.object(runners, "resolve_trigger", return_value={}):
            unknown_pr = pipeline.create_triggered_run(ticket=None, pr=77, sha=None, trigger="pr")
            unknown_sha = pipeline.create_triggered_run(ticket=None, pr=None, sha="abcdef1234567890", trigger="uat-deploy")
        self.assertTrue(unknown_pr["folder"].startswith("pull-requests/pr-77/"))
        self.assertTrue(unknown_sha["folder"].startswith("deploys/abcdef123456/"))
        # Preflight later names the ticket: the index learns it, the folder does not move.
        update_run(unknown_pr["id"], ticket="LEX-1")
        record_outcome(unknown_pr["id"], summary={"passed": 1, "failed": 0}, verdict="PERFECT")
        self.assertEqual(get_run(unknown_pr["id"])["folder"], unknown_pr["folder"])
        self.assertTrue((Path(self.tmp.name) / unknown_pr["folder"] / "manifest.json").is_file())
        self.assertEqual(relocate_legacy_runs(), [])
        self.assertEqual(get_run(unknown_pr["id"])["folder"], unknown_pr["folder"])

    def test_phase1_folder(self):
        created = create_run(ticket=None, pr=None, sha=None, kind="phase1")
        self.assertTrue(created["id"].startswith("regression-"))
        self.assertTrue(created["folder"].startswith("phase-1/"))
        self.assertNotIn("passed", created["folder"])
        self.assertEqual(created["kind"], "phase1")
        self.assertIsNone(created["ticket"])
        folder = Path(self.tmp.name) / created["folder"]
        self.assertTrue((folder / "manifest.json").is_file())
        self.assertFalse((folder / "contents.txt").is_file())
        self.assertFalse((folder / "specs").exists())
        recorded = record_outcome(
            created["id"],
            summary={"passed": 57, "failed": 2, "skipped": 0, "flaky": 0},
            verdict="NEEDS_REVISION",
        )
        # The folder never moves: the result goes into the index and the manifest.
        self.assertEqual(recorded, created["folder"])
        self.assertTrue(folder.is_dir())
        self.assertEqual(get_run(created["id"])["folder"], created["folder"])
        self.assertEqual(get_run(created["id"])["result"], "57 passed, 2 failed, needs revision")
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["result"], "57 passed, 2 failed, needs revision")
        update_run(created["id"], status="queued")
        self.assertEqual(find_active_phase1()["id"], created["id"])
        update_run(created["id"], status="completed")
        self.assertIsNone(find_active_phase1())

    def test_legacy_folder_moves_and_keeps_a_link(self):
        root = Path(self.tmp.name)
        run_id = "regression-20261023T114747Z-f35a"
        legacy = root / "regression" / run_id
        legacy.mkdir(parents=True)
        (legacy / "report.md").write_text("# hi\n", encoding="utf-8")
        (legacy / "qa-result.json").write_text(
            '{"verdict":"NEEDS_REVISION","test_results":{"passed":57,"failed":2,"skipped":0,"flaky":0}}\n',
            encoding="utf-8",
        )
        (root / "index.json").write_text(
            '{"runs":[{"id":"regression-20261023T114747Z-f35a","kind":"phase1","ticket":null,'
            '"status":"needs_revision","createdAt":"2026-10-23T11:47:47.285Z",'
            '"updatedAt":"2026-10-23T12:54:45.001Z"}]}\n',
            encoding="utf-8",
        )
        moved = relocate_legacy_runs()
        self.assertEqual(moved, [run_id])
        folder = get_run(run_id)["folder"]
        self.assertEqual(folder, "phase-1/2026-10-23_1147Z_f35a")
        self.assertEqual(get_run(run_id)["result"], "57 passed, 2 failed, needs revision")
        target = root / folder
        self.assertEqual((target / "report.md").read_text(encoding="utf-8"), "# hi\n")
        self.assertFalse((target / "contents.txt").is_file())
        self.assertTrue(legacy.is_symlink())
        self.assertEqual((legacy / "report.md").read_text(encoding="utf-8"), "# hi\n")
        self.assertEqual(relocate_legacy_runs(), [])


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QA_RUNS_DIR"] = self.tmp.name
        os.environ["LOCAL_MODE"] = "true"
        os.environ.pop("HARNESS_DEPLOY_SECRET", None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_health_and_ticket_shape(self):
        body = health()
        self.assertEqual(body["status"], "ok")
        with self.assertRaises(HTTPException) as raised:
            run_ticket("not-a-ticket")
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(list_runs(), [])
        started = run_phase1()
        self.assertTrue(started["runId"].startswith("regression-"))
        self.assertEqual(get_run(started["runId"])["status"], "queued")
        again = run_phase1()
        self.assertTrue(again["skipped"])
        self.assertEqual(again["runId"], started["runId"])

    def test_a_ticket_queues_one_run_and_no_separate_e2e_run(self):
        queued = run_ticket("LEX-3700")
        rows = list_runs()
        self.assertEqual([row["id"] for row in rows], [queued["runId"]])
        self.assertEqual(rows[0]["kind"], "ticket")
        self.assertEqual(rows[0]["trigger"], "ticket")
        self.assertTrue(rows[0]["folder"].startswith("tickets/LEX-3700/"))
        self.assertNotIn("phase1RunId", queued)


class PersonaTest(unittest.TestCase):
    def test_lookup_stays_on_localhost_and_inside_the_runs_folder(self):
        request = mock.Mock(client=mock.Mock(host="172.17.0.1"))
        with self.assertRaises(HTTPException) as refused:
            internal_lookup(LookupBody(run="/x", ref="LEX-1"), request)
        self.assertEqual(refused.exception.status_code, 403)
        with tempfile.TemporaryDirectory() as raw:
            runs = Path(raw) / "runs"
            (runs / "tickets" / "a").mkdir(parents=True)
            outside = Path(raw) / "outside"
            outside.mkdir()
            settings = mock.Mock(runs=runs, root=Path(raw))
            with mock.patch("app.runners.get_settings", return_value=settings), mock.patch("app.runners.subprocess.run") as started:
                for bad_ref in ("--flag", "../x#1", "LEX-1; rm -rf /", "a/b", ""):
                    self.assertEqual(runners.context_lookup(str(runs / "tickets" / "a"), bad_ref)[0], 400, bad_ref)
                self.assertEqual(runners.context_lookup(str(outside), "LEX-1"), (400, "not a run folder"))
                self.assertEqual(runners.context_lookup(str(runs / "tickets" / "a" / ".." / ".." / ".." / "outside"), "LEX-1"), (400, "not a run folder"))
                started.assert_not_called()
                started.return_value = mock.Mock(returncode=0, stdout='{"line": "ok", "files": []}', stderr="")
                self.assertEqual(runners.context_lookup(str(runs / "tickets" / "a"), "LEX-1"), (0, {"line": "ok", "files": []}))
                # Tokens reach the node half only by its environment, never on the command line.
                self.assertEqual(started.call_args.kwargs["env"]["LOOKUP_DIRECT"], "1")
                started.return_value = mock.Mock(returncode=1, stdout="", stderr="LEX-9 is not named in this run\n")
                self.assertEqual(runners.context_lookup(str(runs / "tickets" / "a"), "LEX-9"), (400, "LEX-9 is not named in this run"))

    def test_persona_login_stays_on_localhost(self):
        self.assertTrue(persona_client_allowed("127.0.0.1"))
        self.assertTrue(persona_client_allowed("::1"))
        self.assertFalse(persona_client_allowed("10.0.0.8"))
        self.assertFalse(persona_client_allowed(None))

    def test_named_persona_in_a_spec_is_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "roles.spec.ts"
            spec.write_text(
                "await injectAuthCookies(page.context())\n"
                "await injectAuthCookies(page.context(), 'viewer')\n"
                "await injectAuthCookies(page.context(), \"support\")\n",
                encoding="utf-8",
            )
            previous = os.environ.get("STYTCH_PERSONA")
            os.environ["STYTCH_PERSONA"] = "admin"
            try:
                self.assertEqual(personas_requested([str(spec)]), ["viewer", "support"])
            finally:
                if previous is None:
                    os.environ.pop("STYTCH_PERSONA", None)
                else:
                    os.environ["STYTCH_PERSONA"] = previous


class CoverageTest(unittest.TestCase):
    def test_checked_in_journeys_are_indexed_without_a_count_floor(self):
        root = Path(__file__).resolve().parents[2] / "e2e test cases"
        cases = load_cases(root)
        by_id = {case.id: case for case in cases}
        self.assertEqual(by_id["TC-DOC-001"].type, "positive")
        self.assertEqual(by_id["TC-DOC-001"].suite, "bvt")
        self.assertEqual(by_id["TC-DOC-009"].type, "negative")
        self.assertEqual(by_id["TC-DOC-009"].suite, "smoke")
        self.assertEqual(by_id["TC-DOC-011"].type, "edge")
        self.assertEqual(by_id["TC-DOC-011"].suite, "regression")
        self.assertEqual(by_id["TC-01"].journey, "search")
        self.assertEqual(by_id["TC-06"].type, "negative")
        self.assertTrue(any(case.journey == "asset crud" and case.type == "negative" and "invalid credentials" in case.title for case in cases))
        self.assertEqual(by_id["AC-035"].journey, "asset crud")
        self.assertEqual(by_id["AC-035"].suite, "smoke")
        self.assertEqual(by_id["AC-036"].type, "positive")
        self.assertEqual(by_id["AC-037"].type, "negative")
        self.assertGreaterEqual(len(cases), 50)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "e2e-coverage.md"
            self.assertEqual(write_coverage_index(root, dest), len(cases))
            text = dest.read_text(encoding="utf-8")
            self.assertIn("no minimum", text)
            self.assertIn("TC-DOC-001", text)
            self.assertIn("search", text)
            self.assertIn("asset crud", text)
            self.assertIn("document editing", text)

    def test_a_title_word_does_not_choose_the_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            journey = Path(tmp) / "widgets"
            journey.mkdir()
            (journey / "widgets.spec.ts").write_text(
                "test.describe('Widgets', () => {\n"
                "  test('TC-1 clears the field and cancels', async () => {})\n"
                "})\n",
                encoding="utf-8",
            )
            (journey / "FEATURE.md").write_text(
                "| TC | Title | Type | Suite |\n"
                "|---|---|---|---|\n"
                "| TC-1 | clears the field and cancels | positive | Smoke |\n",
                encoding="utf-8",
            )
            recorded = load_cases(Path(tmp))
            self.assertEqual(recorded[0].type, "positive")
            self.assertEqual(recorded[0].suite, "smoke")
            (journey / "FEATURE.md").write_text("# no inventory\n", encoding="utf-8")
            guessed = load_cases(Path(tmp))
            self.assertEqual(guessed[0].type, "positive")

    def test_a_rerun_replaces_only_the_tests_it_ran(self):
        def report(file: str, rows: list[tuple[str, str]], describe: str = "") -> dict:
            specs = [{"title": title, "file": file, "tests": [{"status": status}]} for title, status in rows]
            inner = [{"title": describe, "file": file, "specs": specs}] if describe else []
            return {"suites": [{"title": file, "file": file, "specs": [] if describe else specs, "suites": inner}]}

        before = test_outcomes_from_report(report("search.spec.ts", [("TC-01", "expected"), ("TC-06", "unexpected"), ("TC-07", "unexpected")]))
        # The heal renamed TC-07 to TC-07b; the rerun ran TC-06 and the new name only.
        listed = test_outcomes_from_report(report("search.spec.ts", [("TC-01", "skipped"), ("TC-06", "skipped"), ("TC-07b", "skipped")]))
        merged = merge_test_outcomes(before, report("search.spec.ts", [("TC-06", "expected"), ("TC-07b", "expected")]), listed)
        self.assertEqual({k: v["status"] for k, v in merged["search.spec.ts"].items()},
                         {"TC-01": "passed", "TC-06": "passed", "TC-07b": "passed"})
        self.assertEqual(outcome_counts(merged), {"passed": 3, "failed": 0, "skipped": 0, "flaky": 0})
        # Two tests with one title in different describes stay apart.
        both = test_outcomes_from_report(report("a.spec.ts", [("clear selection", "expected")], "Filters"))
        both["a.spec.ts"].update(test_outcomes_from_report(report("a.spec.ts", [("clear selection", "unexpected")], "Bulk"))["a.spec.ts"])
        self.assertEqual(sorted(both["a.spec.ts"]), ["Bulk › clear selection", "Filters › clear selection"])

    def test_server_messages_carry_facts_and_the_rules_live_in_the_phase_files(self):
        text = _lead_prompt(Path("/tmp/runs/tickets/LEX-1/attempt"), "LEX-1", {})
        self.assertTrue(text.startswith("Phase: explore+author"))
        self.assertIn("Ticket: LEX-1", text)
        self.assertIn("phases/explore-author.md", text)
        self.assertLess(len(text.splitlines()), 10)
        # No procedure in the message: counts, tool flags and file contracts are phase-file text.
        for rule in ("at least", "persona.mjs", "coverage.json", "qa-fixtures", "one shell command"):
            self.assertNotIn(rule, text.lower())
        root = Path(__file__).resolve().parents[2]
        skill_dir = root / ".agents/skills/lexful-autonomous-agent-qa"
        # Every phase the server sends has a phase file, and the entry prompt maps each phase to its file.
        entry = (root / ".agents/prompts/qa.md").read_text()
        for phase, name in PHASE_FILES.items():
            self.assertTrue((skill_dir / "phases" / name).is_file(), name)
            self.assertIn(f"phases/{name}", entry)
            self.assertIn(f"`{phase}`", entry)
        for phase in ("ux-audit", "resume"):
            self.assertIn(f"`{phase}`", entry)
        for rule in ("One shell command per call", "Do not spawn subagents"):
            self.assertIn(rule, entry)
        phase_files = {name: (skill_dir / "phases" / name).read_text() for name in set(PHASE_FILES.values())}
        for rule in ("coverage.json", "persona.mjs", "qa-fixtures"):
            self.assertIn(rule, phase_files["explore-author.md"])
        # The e2e heal must not drag in the ticket procedure.
        for ticket_only in ("hypotheses", "feature-map", "coverage.json", "planned-specs"):
            self.assertNotIn(ticket_only, phase_files["e2e-heal.md"])
        self.assertLess(len(phase_files["e2e-heal.md"]), 9000)

    def test_merge_test_outcomes_keeps_unrerun_files(self):
        def report(file: str, rows: list[tuple[str, str]]) -> dict:
            return {
                "suites": [{
                    "file": file,
                    "specs": [
                        {"title": title, "file": file, "tests": [{"status": status}]}
                        for title, status in rows
                    ],
                    "suites": [],
                }],
            }

        bvt = report("specs/move-records-bvt.spec.ts", [("TC-001", "expected")])
        smoke_fail = report("specs/move-records-smoke.spec.ts", [("TC-002", "unexpected")])
        before = test_outcomes_from_report(bvt)
        for file_key, titles in test_outcomes_from_report(smoke_fail).items():
            before.setdefault(file_key, {}).update(titles)
        smoke_pass = report("specs/move-records-smoke.spec.ts", [("TC-002", "expected")])
        merged = merge_test_outcomes(before, smoke_pass)
        self.assertEqual(merged["move-records-bvt.spec.ts"]["TC-001"]["status"], "passed")
        self.assertEqual(merged["move-records-smoke.spec.ts"]["TC-002"]["status"], "passed")

    def test_outcomes_keep_the_tags_the_spec_declared(self):
        report = {"suites": [{"file": "a.spec.ts", "specs": [
            {"title": "TC-1: a", "file": "a.spec.ts", "tags": ["@negative", "@sanity"], "tests": [{"status": "flaky"}]},
        ], "suites": []}]}
        self.assertEqual(test_outcomes_from_report(report), {"a.spec.ts": {"TC-1: a": {"status": "flaky", "tags": ["@negative", "@sanity"]}}})
        self.assertEqual(failed_tests({"suites": [{"specs": [{"title": "t", "ok": False, "tests": [{"status": "unexpected", "results": [
            {"status": "failed", "error": {"message": "\u001b[2mexpect(\u001b[22mreceived).toContain"}}]}]}]}]})[0]["error"],
            "expect(received).toContain")


class BugReportTest(unittest.TestCase):
    BUG = {
        "area": "Documents create drawer",
        "failure": "Create is enabled while the name is empty, and saves a blank document",
        "context": "LEX-3717 document name guard",
        "severity": "High",
        "priority": "P3",
        "severityReason": "A technician can save a document with no name.",
        "description": "The create drawer enables Create while Name is empty. The grid then shows a blank row.",
        "persona": "admin",
        "preconditions": ["Organization E2E Demo exists"],
        "affectedTests": [
            {"id": "TC-LEX-3717-002", "title": "Create is blocked while the name is empty"},
            "TC-LEX-3717-004",
        ],
        "steps": [
            "1. Open https://e2e-test.uat.lexful.net/docs/d/all/system.document",
            "Click New, leave Name empty and click Create",
        ],
        "expected": "Create stays disabled, and no document is written.",
        "actual": "POST /v1/assets/system.document returns 201.",
        "rootCause": "Unknown",
        "evidence": [{"test": "TC-LEX-3717-002", "step": 2, "detail": "expected disabled, received enabled"}],
        "confidence": "confirmed",
    }

    def test_a_bug_reads_as_a_ticket(self):
        filed = record(self.BUG, source="triage", ticket="LEX-3717", url="https://e2e-test.uat.lexful.net",
                       build="4d9b9cf2", when="2026-10-27", screenshots=["bug-evidence/bug-1.png"])
        # The title says what is wrong. The ticket and the test ids are in the body, not the title.
        self.assertEqual(filed["title"], "Documents create drawer: Create is enabled while the name is empty, and saves a blank document")
        self.assertEqual((filed["severity"], filed["priority"]), ("High", "P1"))
        self.assertEqual(filed["steps"][0], "Open https://e2e-test.uat.lexful.net/docs/d/all/system.document")
        self.assertEqual(filed["affectedTests"], ["TC-LEX-3717-002", "TC-LEX-3717-004"])
        text = render_bugs([filed])
        for part in (
            "## Documents create drawer: Create is enabled while the name is empty, and saves a blank document",
            "| High | P1 | confirmed | LEX-3717 · TC-LEX-3717-002, TC-LEX-3717-004 |",
            "**What happens**", "- Signed in as: admin", "**Before you start**", "- Organization E2E Demo exists",
            "**Steps to reproduce**", "1. Open https://e2e-test.uat.lexful.net/docs/d/all/system.document",
            "2. Click New, leave Name empty and click Create", "**Expected**", "**Actual**",
            "**Why it matters**", "A technician can save a document with no name.",
            "- TC-LEX-3717-002 2: expected disabled, received enabled", "![bug-1.png](bug-evidence/bug-1.png)",
        ):
            self.assertIn(part, text)
        self.assertNotIn("P3", text)
        self.assertNotIn("LEX-3717 document name guard", filed["title"])

    def test_a_bug_without_steps_says_so_instead_of_inventing_them(self):
        text = render_bugs([record({"area": "Search", "failure": "x"}, source="triage", ticket="LEX-1", url="u", build="b")])
        self.assertIn("Not recorded by the agent. Replay the affected test: none.", text)
        self.assertNotIn("Repeat the actions", text)

    def test_skipped_and_deprecated_bugs_are_not_filed(self):
        bugs = collect_bugs({
            "failures": [{"class": "spec", "action": "patched", "title": "renamed button"}],
            "bugs": [
                {"title": "Deprecated case", "deprecated": True, "severity": "Low"},
                {"failure": "not reproduced", "status": "skipped"},
            ],
        })
        self.assertEqual(bugs, [])

    def test_a_gap_is_not_filed_even_when_the_healer_also_wrote_a_bug(self):
        bugs = collect_bugs({
            "failures": [{
                "class": "gap",
                "action": "removed",
                "title": "TC-LEX-2328-011: Overview tab shows Embedded",
                "reason": "The document drawer has no Overview tab.",
            }],
            "bugs": [{
                "failure": "The document drawer has no Overview tab",
                "affectedTests": ["TC-LEX-2328-011"],
                "severity": "Low",
            }],
        })
        self.assertEqual(bugs, [])

    def test_an_unclassified_failure_is_an_open_issue_not_a_bug(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            filed = publish_bugs(folder, ticket="LEX-3717", run_id="LEX-3717-1", url="u", build="b", failed=1,
                                 triage={"failures": [{"class": "spec", "title": "TC-LEX-3717-003", "action": "reported"}]})
            self.assertFalse(filed)
            self.assertFalse((folder / "bugs.md").exists())
            self.assertFalse(publish_bugs(folder, ticket="LEX-3717", run_id="r", url="u", build="b", failed=0,
                                          triage={"bugs": [{"area": "Documents", "failure": "gone", "severity": "High"}]}))



class E2EStageTest(unittest.TestCase):
    """The E2E User Journey stage of a ticket run, with Playwright replaced by a stub."""

    def setUp(self):
        root = Path(__file__).resolve().parents[2] / "runs"
        root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        os.environ["QA_RUNS_DIR"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_stage_lives_in_the_ticket_run_and_logs_to_its_run_log(self):
        from unittest import mock
        from app import pipeline, runners, summary
        from app.store import run_dir

        row = create_run(ticket="LEX-3700", pr=None, sha="abc", trigger="uat-deploy")
        folder = run_dir(row["id"])

        def fake_playwright(run_folder, specs, **_):
            Logbook(run_folder).row("playwright", "result", "stub")
            report = {"stats": {"expected": 2}, "suites": [{"file": "search.spec.ts", "specs": [
                {"title": "TC-01: finds", "file": "search.spec.ts", "tags": ["positive", "smoke"], "tests": [{"status": "expected"}]},
                {"title": "TC-02: empty", "file": "search.spec.ts", "tags": ["negative", "smoke"], "tests": [{"status": "expected"}]},
            ]}]}
            (run_folder / "playwright").mkdir(parents=True, exist_ok=True)
            (run_folder / "playwright" / "results.json").write_text(json.dumps(report), encoding="utf-8")
            return {"exitCode": 0, "summary": {"passed": 2, "failed": 0, "skipped": 0, "flaky": 0}}

        with mock.patch.object(runners, "checked_in_specs", return_value=["e2e test cases/search/search.spec.ts"]), \
                mock.patch.object(runners, "write_cli_config", return_value=None), \
                mock.patch.object(runners, "run_playwright", side_effect=fake_playwright):
            pipeline._e2e_stage(row["id"], row, folder, Logbook(folder))
        e2e = folder / "e2e"
        self.assertEqual(json.loads((e2e / "qa-result.json").read_text())["verdict"], "PERFECT")
        outcomes = json.loads((e2e / "playwright" / "test-outcomes.json").read_text())
        self.assertEqual([o["tags"] for o in outcomes], [["positive", "smoke"], ["negative", "smoke"]])
        log = (folder / "run.log").read_text()
        self.assertIn("── E2E User Journey TCs", log)
        self.assertIn("playwright        result          stub", log)
        self.assertFalse((e2e / "run.log").exists())
        phases = [p["name"] for p in summary.get(row["id"]).phases]
        self.assertIn("e2e playwright", phases)
        self.assertEqual(runners._key(e2e), runners._key(folder))
        self.assertEqual([r["id"] for r in list_runs()], [row["id"]])



class HealRerunTest(unittest.TestCase):
    """What runs again after a heal, with Playwright replaced by a stub."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def report(rows):
        return {"suites": [{"title": f, "file": f, "specs": [
            {"title": t, "file": f, "tests": [{"status": st}]} for ff, t, st in rows if ff == f], "suites": []}
            for f in sorted({r[0] for r in rows})]}

    def test_only_the_tests_that_did_not_pass_run_again(self):
        from unittest import mock
        from app import pipeline, runners
        specs = ["e2e test cases/asset crud/assets-crud.spec.ts", "e2e test cases/search/search.spec.ts"]
        outcomes = test_outcomes_from_report(self.report([
            ("assets-crud.spec.ts", "AC-01 opens", "expected"), ("assets-crud.spec.ts", "AC-02 (saves)", "unexpected"),
            ("search.spec.ts", "TC-01", "expected")]))
        calls = []

        def fake_run(folder, files, grep="", **_):
            calls.append((files, grep))
            (folder / "playwright").mkdir(parents=True, exist_ok=True)
            (folder / "playwright" / "results.json").write_text(json.dumps(self.report([
                ("assets-crud.spec.ts", "AC-02 (saves)", "expected"), ("assets-crud.spec.ts", "AC-03 new", "expected")])))
            return {"exitCode": 0, "summary": {}}

        listing = self.report([("assets-crud.spec.ts", "AC-01 opens", "skipped"), ("assets-crud.spec.ts", "AC-02 (saves)", "skipped"),
                               ("assets-crud.spec.ts", "AC-03 new", "skipped")])
        with mock.patch.object(runners, "list_tests", return_value=listing), mock.patch.object(runners, "run_playwright", side_effect=fake_run):
            merged = pipeline._rerun_not_passed(self.folder, specs, outcomes, Logbook(self.folder), 1)
        files, grep = calls[0]
        self.assertEqual(files, ["e2e test cases/asset crud/assets-crud.spec.ts"])
        self.assertEqual(sorted(grep.split("|")), sorted([re.escape("AC-02 (saves)"), re.escape("AC-03 new")]))
        self.assertNotIn("AC-01", grep)
        self.assertEqual(outcome_counts(merged), {"passed": 4, "failed": 0, "skipped": 0, "flaky": 0})

    def test_the_confirm_pass_runs_edited_folders_and_files_still_failing(self):
        from unittest import mock
        from app import pipeline, runners
        from app.settings import get_settings
        root = get_settings().root
        specs = ["e2e test cases/asset crud/assets-crud.spec.ts", "e2e test cases/asset crud/move-records.spec.ts",
                 "e2e test cases/search/search.spec.ts", "e2e test cases/document editing/doceditspec.spec.ts"]
        outcomes = test_outcomes_from_report(self.report([("doceditspec.spec.ts", "TC-DOC-010", "unexpected"),
                                                          ("search.spec.ts", "TC-01", "expected")]))
        seen = []

        def fake_run(folder, files, **_):
            seen.extend(files)
            (folder / "playwright").mkdir(parents=True, exist_ok=True)
            (folder / "playwright" / "results.json").write_text(json.dumps(self.report([("doceditspec.spec.ts", "TC-DOC-010", "unexpected")])))
            return {"exitCode": 1, "summary": {}}

        with mock.patch.object(runners, "run_playwright", side_effect=fake_run):
            pipeline._confirm_after_heals(self.folder, specs, outcomes, {(root / "e2e test cases/asset crud").resolve()}, Logbook(self.folder))
        self.assertEqual(seen, [specs[0], specs[1], specs[3]])

class CliTest(unittest.TestCase):
    def test_bad_arguments_exit_64_without_creating_a_run(self):
        from app.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["QA_RUNS_DIR"] = tmp
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([]), 64)
                self.assertEqual(main(["--ticket", "ABC-1"]), 64)
                self.assertEqual(main(["--e2e", "--sha", "abc"]), 64)
            self.assertEqual(list_runs(), [])

if __name__ == "__main__":
    unittest.main()
