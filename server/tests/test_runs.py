import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.logbook import Logbook, SubagentTail, child_message_lines, format_event, plain_error, session_id_from_text
from app.runners import _preflight_row, _session_expired
from app.main import health, run_phase1, run_ticket
from app.pipeline import (
    failed_tests,
    spec_was_patched,
    startup_order,
    record_suite_edits,
    suite_files_changed,
    suspicious_patches,
    verdict_for,
)
from app.runners import checked_in_specs, common_test_dir, planned_specs
from app.store import (
    create_run,
    find_active_phase1,
    find_active_sha,
    get_run,
    list_runs,
    publish_folder,
    recover_runs,
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
        created = create_run(ticket="LEX-3371", pr=1418, sha="abc123", spec_count=15)
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
        created = create_run(ticket="LEX-3400", pr=None, sha=None, spec_count=None)
        run = Path(self.tmp.name) / created["folder"]
        spec = run / "specs" / "added.spec.ts"
        spec.write_text("import { test } from '@playwright/test'\n")
        found = planned_specs(run, 0)
        self.assertTrue(any(item.endswith("added.spec.ts") for item in found))
        update_run(created["id"], status="agent")
        waiting = create_run(ticket="LEX-3401", pr=None, sha=None, spec_count=None)
        update_run(waiting["id"], status="queued")
        requeued = recover_runs()
        self.assertIn(waiting["id"], requeued)
        self.assertEqual(get_run(created["id"])["status"], "failed")
        self.assertIn("restarted", get_run(created["id"])["error"])

    def test_phase1_folder(self):
        created = create_run(ticket=None, pr=None, sha=None, spec_count=None, kind="phase1")
        self.assertTrue(created["id"].startswith("regression-"))
        self.assertTrue(created["folder"].startswith("phase-1/"))
        self.assertNotIn("passed", created["folder"])
        self.assertEqual(created["kind"], "phase1")
        self.assertIsNone(created["ticket"])
        folder = Path(self.tmp.name) / created["folder"]
        self.assertTrue((folder / "manifest.json").is_file())
        self.assertTrue((folder / "contents.txt").read_text(encoding="utf-8").startswith("This folder is one phase 1"))
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


if __name__ == "__main__":
    unittest.main()
