import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.logbook import (
    Logbook,
    SubagentTail,
    child_message_lines,
    echo_run,
    format_event,
    plain_error,
    session_id_from_text,
)
from app.runners import _preflight_row, _session_expired
from app.main import health, persona_client_allowed, run_phase1, run_ticket
from app.bugs import collect_bugs, publish_bugs, render_bugs
from app.coverage import load_cases, write_coverage_index
from app.pipeline import (
    _lead_prompt,
    failed_tests,
    merge_outcomes,
    outcomes_by_file,
    spec_was_patched,
    specs_for_failures,
    startup_order,
    record_suite_edits,
    suite_files_changed,
    suspicious_patches,
    verdict_for,
)
from app.runners import checked_in_specs, common_test_dir, personas_requested, planned_specs
from app.store import (
    attach_e2e_log,
    create_run,
    find_active_phase1,
    find_active_sha,
    get_run,
    list_runs,
    publish_folder,
    recover_runs,
    share_e2e_log,
    relocate_legacy_runs,
    update_run,
)


class LogbookTest(unittest.TestCase):
    def test_tool_and_error_lines(self):
        self.assertIsNone(format_event({"type": "step_start"}))
        shell = format_event({
            "type": "tool_use",
            "part": {"tool": "shell", "state": {"status": "completed", "input": {"command": "ls explore"}}},
        })
        self.assertIn("qa", shell)
        self.assertIn("shell", shell)
        self.assertIn("ls explore", shell)
        subagent = format_event({
            "type": "tool_use",
            "part": {
                "tool": "subagent",
                "state": {
                    "status": "error",
                    "input": {"agent": "qa-explorer", "description": "Explore the drawer", "prompt": "long prompt"},
                    "error": "Subagent failed (sessionID: ses_abc): Provider returned error",
                    "time": {"start": 1_000, "end": 61_000},
                },
            },
        })
        self.assertIn("qa-explorer", subagent)
        self.assertIn("Explore the drawer", subagent)
        self.assertIn("Provider returned error", subagent)
        self.assertIn("1m 00s", subagent)
        self.assertNotIn("long prompt", subagent)
        self.assertIn("ses", format_event({"type": "error", "error": {"message": "Expected a string starting with ses"}}))
        hidden = format_event({
            "type": "error",
            "error": {"message": "budget https://openrouter.ai/workspaces/lexful/keys/secret"},
        })
        self.assertNotIn("keys/secret", hidden)
        self.assertIn("openrouter", hidden)

    def test_child_message_names_the_action(self):
        lines = child_message_lines("qa-explorer", {
            "content": [
                {"type": "reasoning", "text": "hidden chain of thought"},
                {
                    "type": "tool",
                    "name": "shell",
                    "state": {
                        "status": "completed",
                        "input": {"command": "cd /tmp/lexful-qa-opencode/explore && playwright-cli open https://e2e-test.uat.lexful.net"},
                    },
                },
                {"type": "text", "text": "Opened the contacts list and found the Relationships tab."},
            ],
        })
        self.assertTrue(any("playwright-cli open https://e2e-test.uat.lexful.net" in line for line in lines))
        self.assertTrue(any("Relationships tab" in line for line in lines))
        self.assertFalse(any("chain of thought" in line for line in lines))
        self.assertFalse(any("cd /tmp" in line for line in lines))

    def test_subagent_tail_writes_child_tools_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            database = folder / "opencode.db"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE session_v2 (
                    id text PRIMARY KEY, project_id text NOT NULL, parent_id text, slug text NOT NULL,
                    directory text NOT NULL, title text, version text NOT NULL, cost real DEFAULT 0,
                    tokens_input integer DEFAULT 0, tokens_output integer DEFAULT 0, tokens_reasoning integer DEFAULT 0,
                    time_created integer NOT NULL, time_updated integer NOT NULL, time_idle integer, agent text
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE session_message (
                    id text PRIMARY KEY, session_id text NOT NULL, type text NOT NULL, seq integer NOT NULL,
                    time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO session_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("ses_child", "project", "ses_parent", "slug", "/work", "Phase 1", "1", 0.4, 10, 20, 0, 1_000, 5_000, None, "qa-explorer"),
            )
            payload = {
                "content": [{
                    "type": "tool",
                    "name": "read",
                    "state": {"status": "completed", "input": {"path": "/work/lexful-qa-opencode/runs/demo/context-pack.json"}},
                }],
            }
            connection.execute(
                "INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
                ("msg1", "ses_child", "assistant", 1, 1_000, 2_000, json.dumps(payload)),
            )
            connection.commit()
            connection.close()
            book = Logbook(folder)
            tail = SubagentTail("ses_parent", book, database)
            tail.opened_at = 0
            tail.poll()
            tail.poll()
            text = (folder / "run.log").read_text(encoding="utf-8")
            self.assertEqual(text.count("qa-explorer"), 2)
            self.assertIn("started", text)
            self.assertIn("runs/demo/context-pack.json", text)
            self.assertNotIn("finished", text)
            connection = sqlite3.connect(database)
            connection.execute("UPDATE session_v2 SET time_idle = 61000, cost = 0.4 WHERE id = 'ses_child'")
            connection.commit()
            connection.close()
            tail.poll()
            text = (folder / "run.log").read_text(encoding="utf-8")
            self.assertEqual(text.count("finished"), 1)
            self.assertIn("$0.4000", text)
            self.assertEqual(text.count("context-pack.json"), 1)

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
        self.assertTrue((folder / "contents.txt").is_file())
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
        spec.write_text("import { test } from '@playwright/test'\n")
        found = planned_specs(run, 0)
        self.assertTrue(any(item.endswith("added.spec.ts") for item in found))
        update_run(created["id"], status="agent")
        waiting = create_run(ticket="LEX-3401", pr=None, sha=None)
        update_run(waiting["id"], status="queued")
        requeued = recover_runs()
        self.assertIn(waiting["id"], requeued)
        failed = get_run(created["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("restarted", failed["error"])
        report = Path(self.tmp.name) / failed["folder"] / "report.md"
        self.assertIn("restarted", report.read_text(encoding="utf-8"))
        self.assertTrue((report.parent / "qa-result.json").is_file())

    def test_e2e_log_is_stored_on_the_ticket(self):
        phase1 = create_run(ticket=None, pr=None, sha=None, kind="phase1")
        phase1_dir = Path(self.tmp.name) / phase1["folder"]
        (phase1_dir / "run.log").write_text("e2e line\n", encoding="utf-8")
        (phase1_dir / "report.md").write_text("# journey\n", encoding="utf-8")
        update_run(phase1["id"], status="completed")
        waiting = create_run(ticket="LEX-3500", pr=None, sha=None)
        update_run(waiting["id"], status="queued")
        self.assertEqual(share_e2e_log(phase1["id"]), [waiting["id"]])
        saved = Path(self.tmp.name) / waiting["folder"] / "e2e" / "run.log"
        self.assertEqual(saved.read_text(encoding="utf-8"), "e2e line\n")
        self.assertTrue((saved.parent / "report.md").is_file())
        later = create_run(ticket="LEX-3501", pr=None, sha=None)
        later_dir = Path(self.tmp.name) / later["folder"]
        self.assertTrue(attach_e2e_log(later_dir))
        self.assertIn("e2e line", (later_dir / "e2e" / "run.log").read_text(encoding="utf-8"))
        self.assertFalse(attach_e2e_log(later_dir))

    def test_phase1_folder(self):
        created = create_run(ticket=None, pr=None, sha=None, kind="phase1")
        self.assertTrue(created["id"].startswith("regression-"))
        self.assertTrue(created["folder"].startswith("phase-1/"))
        self.assertNotIn("passed", created["folder"])
        self.assertEqual(created["kind"], "phase1")
        self.assertIsNone(created["ticket"])
        folder = Path(self.tmp.name) / created["folder"]
        self.assertTrue((folder / "manifest.json").is_file())
        self.assertTrue((folder / "contents.txt").read_text(encoding="utf-8").startswith("This folder is one E2E User Journey"))
        self.assertFalse((folder / "specs").exists())
        published = publish_folder(
            created["id"],
            summary={"passed": 57, "failed": 2, "skipped": 0, "flaky": 0},
            verdict="NEEDS_REVISION",
        )
        self.assertIn("57-passed_2-failed_needs-revision", published)
        self.assertTrue((Path(self.tmp.name) / published / "report.md").exists() or (Path(self.tmp.name) / published / "manifest.json").is_file())
        self.assertFalse(folder.exists())
        self.assertEqual(get_run(created["id"])["folder"], published)
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
        self.assertEqual(
            folder,
            "phase-1/2026-10-23_1147Z_f35a_57-passed_2-failed_needs-revision",
        )
        target = root / folder
        self.assertEqual((target / "report.md").read_text(encoding="utf-8"), "# hi\n")
        self.assertTrue((target / "contents.txt").is_file())
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


class PersonaTest(unittest.TestCase):
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

    def test_failed_file_counts_replace_only_that_file(self):
        def report(file: str, results: list[tuple[str, str]]) -> dict:
            return {"suites": [{"file": file, "specs": [
                {"title": title, "ok": status == "expected", "file": file, "tests": [{"status": status}]}
                for title, status in results
            ], "suites": []}]}

        before = outcomes_by_file(report("search/search.spec.ts", [("TC-01", "expected"), ("TC-06", "unexpected")]))
        before.update(outcomes_by_file(report("asset crud/assets-crud.spec.ts", [("AC-011", "expected")])))
        after = outcomes_by_file(report("search/search.spec.ts", [("TC-01", "expected"), ("TC-06", "expected")]))
        merged = merge_outcomes(before, after, ["e2e test cases/search/search.spec.ts"])
        self.assertEqual(merged, {"passed": 3, "failed": 0, "skipped": 0, "flaky": 0})
        failed = report("search/search.spec.ts", [("TC-06", "unexpected")])
        self.assertEqual(
            specs_for_failures(
                ["e2e test cases/search/search.spec.ts", "e2e test cases/asset crud/assets-crud.spec.ts"],
                failed,
            ),
            ["e2e test cases/search/search.spec.ts"],
        )

    def test_lead_prompt_has_no_floor_and_points_at_coverage(self):
        text = _lead_prompt(Path("/tmp/runs/tickets/LEX-1/attempt"), "LEX-1", {})
        self.assertNotIn("at least", text.lower())
        self.assertNotIn("15", text)
        self.assertIn("e2e-coverage.md", text)
        self.assertIn("no minimum and no maximum", text)
        self.assertIn("node scripts/persona.mjs support", text)


class BugReportTest(unittest.TestCase):
    def test_bug_record_uses_the_required_format_and_groups_cases(self):
        text = render_bugs(
            [{
                "area": "Documents",
                "failure": "Create stays enabled when the name is empty",
                "context": "LEX-3717 document name guard",
                "severity": "High",
                "priority": "P3",
                "severityReason": "A technician can save a document with no name.",
                "description": "The create drawer enables Create while Name is empty. The grid then shows a blank row.",
                "affectedTests": [
                    {"id": "TC-LEX-3717-002", "suite": "Smoke", "title": "Create is blocked while the name is empty", "note": "Create stayed enabled"},
                    {"id": "TC-LEX-3717-004", "suite": "Regression", "title": "Reload keeps the blank name", "note": "Blank name survived reload"},
                ],
                "steps": [
                    "Navigate to https://e2e-test.uat.lexful.net/docs/d/all/system.document as Admin",
                    "Leave Name empty and click Create",
                ],
                "expected": "Create stays disabled, and no document is written.",
                "actual": "POST /v1/assets/system.document returns 201.",
                "rootCause": "Unknown — requires investigation",
                "evidence": [{"test": "TC-LEX-3717-002", "step": 2, "detail": "expected disabled, received enabled"}],
                "labels": ["documents", "create"],
            }],
            ticket="LEX-3717",
            url="https://e2e-test.uat.lexful.net",
            build="unknown",
            when="2026-10-27",
            cycle="LEX-3717-cycle-1",
        )
        self.assertIn("Title:          Documents — Create stays enabled when the name is empty — LEX-3717 document name guard", text)
        self.assertIn("Type:           Bug", text)
        self.assertIn("Severity:       High", text)
        self.assertIn("Priority:       P1", text)
        self.assertNotIn("P3", text)
        self.assertIn("A technician can save a document with no name.", text)
        self.assertNotIn("Severity reason:", text)
        self.assertIn("URL:     https://e2e-test.uat.lexful.net", text)
        self.assertIn("Build:   unknown", text)
        self.assertIn("Date:    2026-10-27", text)
        self.assertNotIn("Affected test cases:", text)
        self.assertNotIn("Execution cycle:", text)
        self.assertIn("1. Navigate to https://e2e-test.uat.lexful.net/docs/d/all/system.document as Admin", text)
        self.assertIn("Expected Result:", text)
        self.assertIn("Actual Result:", text)
        self.assertIn("Root Cause:", text)
        self.assertIn("Unknown — requires investigation", text)
        self.assertIn("- [TC-LEX-3717-002 step 2]: expected disabled, received enabled", text)
        self.assertNotIn("Fix Version:", text)
        self.assertIn("qa-generated", text)
        self.assertIn("regression", text)
        self.assertNotIn("Affected Test Cases Detail:", text)

    def test_skipped_and_spec_failures_are_not_filed(self):
        bugs = collect_bugs({
            "failures": [
                {"class": "spec", "action": "patched", "title": "renamed button"},
                {"class": "bug", "action": "skipped", "title": "deprecated path"},
                {"class": "bug", "action": "reported", "title": "Deprecated: old drawer", "deprecated": True},
            ],
            "bugs": [
                {"title": "Deprecated case", "deprecated": True, "severity": "Low"},
            ],
        }, [{"title": "renamed button", "file": "e2e test cases/search/search.spec.ts", "error": "locator"}])
        self.assertEqual(bugs, [])

    def test_unclassified_failure_still_gets_a_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            wrote = publish_bugs(
                folder,
                ticket="LEX-3717",
                run_id="LEX-3717-1",
                url="https://e2e-test.uat.lexful.net",
                build="unknown",
                failed=1,
                triage={},
                still_failing=[{
                    "title": "TC-LEX-3717-003: reload drops the tag",
                    "file": "runs/tickets/LEX-3717/specs/documents-sanity.spec.ts",
                    "error": "expected tag, received none",
                }],
                when="2026-10-27",
                cycle=2,
            )
            self.assertTrue(wrote)
            text = (folder / "bugs.md").read_text(encoding="utf-8")
            self.assertIn("Severity:       Medium", text)
            self.assertIn("Priority:       P2", text)
            self.assertIn("- [TC-LEX-3717-003 step 1]: expected tag, received none", text)
            self.assertIn("Medium until the impact is confirmed.", text)
            self.assertFalse(publish_bugs(
                folder,
                ticket="LEX-3717",
                run_id="LEX-3717-1",
                url="https://e2e-test.uat.lexful.net",
                build="unknown",
                failed=0,
                triage={"bugs": [{"area": "Documents", "failure": "gone", "severity": "High"}]},
                still_failing=[],
            ))


if __name__ == "__main__":
    unittest.main()
