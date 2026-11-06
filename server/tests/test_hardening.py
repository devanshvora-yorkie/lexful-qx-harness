"""Security hardening and the verdict rules added after the run review (2026-11-06)."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app import checks, pipeline, runners, safefs, store


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


class RunsDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "runs"
        self.root.mkdir()
        self.env = mock.patch.dict(os.environ, {"QA_RUNS_DIR": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class SafeWriteTest(RunsDir):
    def test_a_planted_symlink_is_replaced_not_followed(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        run = self.root / "tickets" / "LEX-1" / "r"
        run.mkdir(parents=True)
        (run / "run.log").symlink_to(outside)
        (run / "run.log").write_text("server line\n", encoding="utf-8")
        with (run / "run.log").open("a", encoding="utf-8") as handle:
            handle.write("more\n")
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        self.assertFalse((run / "run.log").is_symlink())
        self.assertEqual((run / "run.log").read_text(encoding="utf-8"), "server line\nmore\n")

    def test_a_parent_folder_swapped_for_a_symlink_is_refused(self):
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        (self.root / "e2e").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(safefs.UnsafePath):
            (self.root / "e2e" / "qa-result.json").write_text("{}", encoding="utf-8")
        self.assertEqual(list(outside.iterdir()), [])

    def test_ordinary_writes_and_reads_still_work(self):
        target = self.root / "phase-1" / "x" / "a.json"
        target.parent.mkdir(parents=True)
        target.write_text("{}", encoding="utf-8")
        target.write_bytes(b"[1]")
        self.assertEqual(target.read_text(encoding="utf-8"), "[1]")
        self.assertEqual(safefs.read_bytes(target), b"[1]")

    def test_read_bytes_refuses_a_symlink(self):
        secret = Path(self.tmp.name) / "environ"
        secret.write_text("TOKEN=x", encoding="utf-8")
        link = self.root / "shot.png"
        link.symlink_to(secret)
        with self.assertRaises(OSError):
            safefs.read_bytes(link)


class IndexFolderTest(RunsDir):
    def test_only_folders_the_server_makes_are_accepted(self):
        self.assertEqual(store.safe_folder("tickets/LEX-12/2026-11-06_1000Z_ab12"), "tickets/LEX-12/2026-11-06_1000Z_ab12")
        self.assertEqual(store.safe_folder("phase-1/2026-11-06_1000Z_ab12"), "phase-1/2026-11-06_1000Z_ab12")
        self.assertIsNone(store.safe_folder("../../root"))
        self.assertIsNone(store.safe_folder("tickets/LEX-1/../../x"))
        self.assertIsNone(store.safe_folder("/etc/x"))

    def test_run_dir_refuses_a_tampered_index(self):
        write(self.root / "index.json", {"runs": [{"id": "LEX-1-x", "folder": "../../etc"}]})
        with self.assertRaises(ValueError):
            store.run_dir("LEX-1-x")


class GitAndEnvTest(unittest.TestCase):
    def test_every_server_git_command_disables_hooks_and_fsmonitor(self):
        env = runners.git_safe_env()
        pairs = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
        self.assertEqual(pairs["core.hooksPath"], "/dev/null")
        self.assertEqual(pairs["core.fsmonitor"], "false")
        self.assertEqual(pairs["protocol.allow"], "never")

    def test_the_token_header_is_added_after_the_hardening(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t0k"}):
            env = runners._git_env()
        keys = [env[f"GIT_CONFIG_KEY_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))]
        self.assertIn("core.hooksPath", keys)
        self.assertEqual(keys[-1], "http.extraHeader")
        self.assertNotIn("GITHUB_TOKEN", env)

    def test_agent_env_drops_anything_that_looks_like_a_secret(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "x", "AWS_SECRET_ACCESS_KEY": "y", "SOME_TOKEN": "z",
                                          "QA_PW_WORKERS": "3", "STYTCH_ADMIN_EMAIL": "a@b"}):
            env = runners.scrubbed_env()
        for name in ("OPENROUTER_API_KEY", "AWS_SECRET_ACCESS_KEY", "SOME_TOKEN"):
            self.assertNotIn(name, env)
        self.assertEqual(env["QA_PW_WORKERS"], "3")

    def test_opencode_env_has_the_tool_path_and_a_writable_tmp(self):
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(runners, "agent_identity", return_value=None):
            env = runners._opencode_env(Path(raw))
            self.assertTrue(env["PATH"].split(os.pathsep)[0].endswith("node_modules/.bin"))
            self.assertEqual(env["TMPDIR"], str(Path(raw) / "tmp"))
            self.assertTrue((Path(raw) / "tmp").is_dir())

    def test_session_check_runs_at_most_once_in_five_minutes(self):
        runners._LAST_SESSION_CHECK[0] = 0.0
        calls = []
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw) / "session.json"
            write(Path(raw) / "admin.json", "{}")
            with mock.patch.object(runners, "session_state_path", return_value=cache), \
                 mock.patch.object(runners, "ensure_session", side_effect=lambda persona=None, **_: calls.append(persona) or (0, "session reused")):
                runners.keep_sessions_fresh()
                runners.keep_sessions_fresh()
        self.assertEqual(calls, ["admin"])
        runners._LAST_SESSION_CHECK[0] = time.time() - 400
        self.assertTrue(runners.SESSION_CHECK_GAP_SECONDS <= 400)


class VerdictRulesTest(unittest.TestCase):
    def test_an_e2e_stage_that_did_not_pass_blocks_the_ticket(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.assertEqual(pipeline.e2e_stage_blockers(folder), [])
            write(folder / "e2e" / "qa-result.json", {"verdict": "NEEDS_REVISION", "test_results": {"passed": 60, "failed": 2},
                                                      "open_issues": ["bug: search drops results"]})
            lines = pipeline.e2e_stage_blockers(folder)
            self.assertEqual(len(lines), 1)
            self.assertIn("E2E User Journey TCs NEEDS_REVISION", lines[0])
            self.assertIn("search drops results", lines[0])
            write(folder / "e2e" / "qa-result.json", {"verdict": "PERFECT"})
            self.assertEqual(pipeline.e2e_stage_blockers(folder), [])

    def test_a_filed_bug_blocks_sign_off(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.assertEqual(pipeline.filed_bug_blockers(folder), [])
            write(folder / "bugs.json", {"bugs": [{"title": "API: wrong record changed"}]})
            self.assertIn("1 product bug(s) filed", pipeline.filed_bug_blockers(folder)[0])

    def test_a_test_the_healer_left_for_a_person_but_that_passed_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "triage.json", {"failures": [{"test": "TC-1", "class": "spec", "action": "reported", "reason": "oracle unclear"}]})
            write(folder / "playwright" / "test-outcomes.json", [{"file": "a.spec.ts", "title": "s › TC-1: counts rows", "status": "passed"}])
            lines = pipeline.reported_but_passed(folder)
            self.assertEqual(len(lines), 1)
            self.assertIn("TC-1 passed after the healer left it", lines[0])

    def test_a_pass_then_a_confirm_failure_in_an_untouched_folder_is_unstable(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            root = pipeline.get_settings().root
            files = ["e2e test cases/document editing/doceditspec.spec.ts", "e2e test cases/asset crud/assets-crud.spec.ts"]
            before = {"doceditspec.spec.ts": {"TC-DOC-001": {"status": "passed"}, "TC-DOC-010": {"status": "failed"}},
                      "assets-crud.spec.ts": {"drawer": {"status": "passed"}}}
            after = {"doceditspec.spec.ts": {"TC-DOC-001": {"status": "failed"}, "TC-DOC-010": {"status": "failed"}},
                     "assets-crud.spec.ts": {"drawer": {"status": "failed"}}}
            edited = {(root / "e2e test cases/asset crud").resolve()}
            merged = pipeline.mark_unstable(folder, before, after, files, edited)
            self.assertEqual(merged["doceditspec.spec.ts"]["TC-DOC-001"]["status"], "flaky")  # untouched folder
            self.assertEqual(merged["doceditspec.spec.ts"]["TC-DOC-010"]["status"], "failed")  # failed before too
            self.assertEqual(merged["assets-crud.spec.ts"]["drawer"]["status"], "failed")       # a heal edited its folder
            self.assertIn("TC-DOC-001", pipeline.unstable_notes(folder)[0])

    def test_an_edit_in_the_same_folder_that_the_spec_does_not_import_keeps_it_unstable(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            suite = folder / "suite"
            write(suite / "crud.spec.ts", "import { Drawer } from './drawer-pom'\n")
            write(suite / "drawer-pom.ts", "export class Drawer {}\n")
            write(suite / "move.spec.ts", "import { Move } from './move-pom'\n")
            write(suite / "move-pom.ts", "export class Move {}\n")
            with mock.patch.object(pipeline, "get_settings", return_value=mock.Mock(root=folder)):
                before = {"crud.spec.ts": {"drawer": {"status": "passed"}}, "move.spec.ts": {"move": {"status": "passed"}}}
                after = {"crud.spec.ts": {"drawer": {"status": "failed"}}, "move.spec.ts": {"move": {"status": "failed"}}}
                merged = pipeline.mark_unstable(folder, before, after, ["suite/crud.spec.ts", "suite/move.spec.ts"],
                                                {suite.resolve()}, None, {(suite / "move-pom.ts").resolve()})
            self.assertEqual(merged["crud.spec.ts"]["drawer"]["status"], "flaky")   # the heal edited a file it does not import
            self.assertEqual(merged["move.spec.ts"]["move"]["status"], "failed")    # the heal edited its page object

    def test_decisions_match_by_id_or_title(self):
        decisions = [{"test": "TC-DOC-010", "note": "default name"}]
        self.assertIsNotNone(pipeline.decision_for("Document editing — negative › TC-DOC-010: Creating ...", decisions))
        self.assertIsNotNone(pipeline.decision_for("TC-DOC-010", decisions))
        self.assertIsNone(pipeline.decision_for("TC-DOC-0101: other", decisions))
        outcomes = {"a.spec.ts": {"x › TC-DOC-010: y": {"status": "failed"}, "x › TC-DOC-001: z": {"status": "failed"}}}
        self.assertEqual(pipeline.decided_failures(outcomes, decisions), ["TC-DOC-010: default name"])

    def test_bugs_of_decided_cases_are_not_filed(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "bugs.json", {"bugs": [
                {"title": "Docs: empty name accepted", "affectedTests": ["TC-DOC-010"], "expected": "e", "actual": "a"},
                {"title": "Search: broken", "affectedTests": ["TC-01"], "expected": "e", "actual": "a"},
            ]})
            dropped = pipeline._drop_decided_bugs(folder, [{"test": "TC-DOC-010", "note": ""}])
            self.assertEqual(dropped, 1)
            kept = json.loads((folder / "bugs.json").read_text(encoding="utf-8"))["bugs"]
            self.assertEqual([b["title"] for b in kept], ["Search: broken"])
            self.assertNotIn("empty name", (folder / "bugs.md").read_text(encoding="utf-8"))


class HandoffAndLintTest(unittest.TestCase):
    def test_missing_and_incomplete_handoff_files_are_listed(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "context-pack.json", {"ticket": {"acceptanceCriteria": "one\ntwo\nthree"}})
            write(folder / "coverage.json", {"criteria": [{"ac": "AC1", "na": "heading"}]})
            write(folder / "hypotheses.json", {"hypotheses": [{"id": "H1", "outcome": "planned"}]})
            problems = checks.handoff_problems(folder)
            text = "\n".join(problems)
            self.assertIn("coverage.json does not list AC2, AC3", text)
            self.assertIn("hypothesis H1 has no outcome", text)
            self.assertIn("affected-cases.json is missing", text)
            self.assertIn("planned-specs.json is missing", text)

    def test_a_complete_handoff_has_no_problems(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "context-pack.json", {"ticket": {"acceptanceCriteria": "one"}})
            write(folder / "coverage.json", [{"ac": "AC1", "tests": ["TC-1"]}])  # a bare list is accepted too
            write(folder / "hypotheses.json", {"hypotheses": [{"id": "H1", "outcome": "refuted"}]})
            for name in ("affected-cases.json", "api-findings.json", "planned-specs.json"):
                write(folder / name, {})
            self.assertEqual(checks.handoff_problems(folder), [])

    def test_lint_flags_the_patterns_that_broke_runs(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "specs" / "a-pom.ts", "\n".join([
                "const rows = page.locator('.ag-row [role=checkbox]')",
                "await page.waitForTimeout(5000)",
                "await page.waitForTimeout(300)",
                "// page.locator('[role=checkbox]') in a comment is fine",
                "await page.goto(url, { waitUntil: 'networkidle' })",
                "await page.getByRole('checkbox').check()",
            ]))
            found = checks.spec_lint(folder)
            self.assertEqual(len(found), 3)
            self.assertTrue(found[0].startswith("specs/a-pom.ts:1:"))
            self.assertIn("specs/a-pom.ts:2:", found[1])
            self.assertIn("specs/a-pom.ts:5:", found[2])

    def test_the_browser_config_sets_short_action_timeouts(self):
        with tempfile.TemporaryDirectory() as raw, \
             mock.patch.object(runners.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="/ms-playwright/chrome\n")):
            target = runners.write_cli_config(Path(raw))
            config = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(config["timeouts"], {"action": 10_000, "navigation": 30_000})


class RepairTurnTest(unittest.TestCase):
    def test_no_repair_turn_when_the_handoff_is_complete(self):
        with tempfile.TemporaryDirectory() as raw, \
             mock.patch.object(checks, "handoff_problems", return_value=[]), \
             mock.patch.object(checks, "spec_lint", return_value=[]), \
             mock.patch.object(runners, "run_opencode") as run:
            pipeline._repair_handoff("r", Path(raw), mock.Mock(), "LEX-1", "ses_1")
        run.assert_not_called()

    def test_one_repair_turn_in_the_explore_session_lists_each_problem(self):
        with tempfile.TemporaryDirectory() as raw, \
             mock.patch.object(checks, "handoff_problems", side_effect=[["coverage.json is missing"], []]), \
             mock.patch.object(checks, "spec_lint", side_effect=[["specs/a.ts:1: use getByRole"], []]), \
             mock.patch.object(pipeline, "_suite_files", return_value={}), \
             mock.patch.object(pipeline, "_guard_suite"), \
             mock.patch.object(pipeline, "_check_cancel"), \
             mock.patch.object(runners, "run_opencode", return_value=(0, "ses_1")) as run:
            book = mock.Mock()
            pipeline._repair_handoff("r", Path(raw), book, "LEX-1", "ses_1")
        run.assert_called_once()
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["session_id"], "ses_1")
        self.assertEqual(kwargs["log_name"], "agent-repair.jsonl")
        self.assertIn("coverage.json is missing", kwargs["prompt"])
        self.assertIn("use getByRole", kwargs["prompt"])
        self.assertIn("repaired", book.row.call_args_list[-1].args[2])


if __name__ == "__main__":
    unittest.main()
