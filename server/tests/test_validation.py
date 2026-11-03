"""Inputs that become folder names or command arguments are checked before they are used."""

import argparse
import os
import tempfile
import unittest
from unittest import mock

from fastapi import HTTPException

from app.cli import _pr, _sha, _ticket
from app.main import DeployBody, RUN_ID_RE, SHA_RE, TICKET_RE, run_detail, run_log, uat_deploy
from app.settings import get_settings
from app.store import create_run, relative_folder


class CommitIdTest(unittest.TestCase):
    def test_only_a_commit_id_is_accepted(self):
        for good in ("f9251b0", "F9251B0EC12BA8BDFE950293ACFE124C7BDAA92D", "a" * 40):
            self.assertTrue(SHA_RE.match(good), good)
        for bad in ("../../x", "f9251b0/../..", "f9251b", "g" * 12, "a" * 41, "", "--help", "abc def0", "f9251b0\n"):
            self.assertIsNone(SHA_RE.match(bad), bad)

    def test_the_cli_takes_the_same_commit_ids(self):
        self.assertEqual(_sha(" F9251B0EC12B "), "f9251b0ec12b")
        for bad in ("../x", "xyz1234", "abc"):
            with self.assertRaises(argparse.ArgumentTypeError):
                _sha(bad)

    def test_the_cli_takes_only_plain_numbers_and_tickets(self):
        self.assertEqual(_pr("2245"), 2245)
        self.assertEqual(_ticket("lex-3642"), "LEX-3642")
        for bad in ("0", "-1", "12a", "١٢٣"):  # the last is Arabic-Indic digits
            with self.assertRaises(argparse.ArgumentTypeError):
                _pr(bad)
        for bad in ("LEX-", "LEX-١٢٣", "ABC-1", "LEX-1; ls"):
            with self.assertRaises(argparse.ArgumentTypeError):
                _ticket(bad)

    def test_the_ticket_pattern_is_ascii_only(self):
        self.assertTrue(TICKET_RE.match("LEX-3642"))
        self.assertTrue(TICKET_RE.match("lex-3642"))
        self.assertIsNone(TICKET_RE.match("LEX-١٢٣"))
        self.assertIsNone(TICKET_RE.match("LEX-1\n"))


class FolderTest(unittest.TestCase):
    def test_a_deploy_folder_is_made_only_from_a_real_commit_id(self):
        row = {"id": "x-20261103T000000Z-ab12", "createdAt": "2026-11-03T09:28:58.559Z", "sha": "F9251B0EC12BA8BD"}
        self.assertTrue(relative_folder(row).startswith("deploys/f9251b0ec12b/"))
        for hostile in ("../../../etc", "..", "a/b", "f9251b0\n../x"):
            folder = relative_folder({**row, "sha": hostile})
            self.assertTrue(folder.startswith("manual/"), (hostile, folder))
            self.assertNotIn("..", folder)


class ApiInputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QA_RUNS_DIR"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_deploy_with_a_hostile_sha_is_refused(self):
        for bad in ("../../x", "not-a-sha", "a" * 41):
            with self.assertRaises(HTTPException) as caught:
                uat_deploy(DeployBody(sha=bad))
            self.assertEqual(caught.exception.status_code, 400)

    def test_run_ids_are_checked_before_they_touch_the_disk(self):
        self.assertTrue(RUN_ID_RE.match("pr-2245-20261103T092858Z-bc40"))
        for bad in ("..", ".hidden", "a/b", "a b", "", "x" * 200, "run-1\n"):
            self.assertIsNone(RUN_ID_RE.match(bad), bad)
        with self.assertRaises(HTTPException) as caught:
            run_log("..")
        self.assertEqual(caught.exception.status_code, 400)
        with self.assertRaises(HTTPException) as caught:
            run_detail("pr-1-20261103T000000Z-ffff")
        self.assertEqual(caught.exception.status_code, 404)

    def test_a_known_run_has_a_valid_id(self):
        row = create_run(ticket="LEX-3642", pr=None, sha=None)
        self.assertTrue(RUN_ID_RE.match(row["id"]), row["id"])


class SettingsTest(unittest.TestCase):
    def test_a_bad_number_in_env_falls_back_instead_of_stopping_the_server(self):
        bad = {
            "QA_SERVER_PORT": "eight",
            "QA_AGENT_TIMEOUT_SECONDS": "soon",
            "QA_PLAYWRIGHT_TIMEOUT_SECONDS": "",
            "QA_HEAL_ATTEMPTS": "three",
        }
        with mock.patch.dict(os.environ, bad):
            settings = get_settings()
        self.assertEqual(settings.port, 8787)
        self.assertEqual(settings.agent_timeout_seconds, 2700)
        self.assertEqual(settings.playwright_timeout_seconds, 2700)
        self.assertEqual(settings.heal_attempts, 3)

    def test_there_is_one_model(self):
        self.assertFalse(hasattr(get_settings(), "sub_model"))


if __name__ == "__main__":
    unittest.main()
