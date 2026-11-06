import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import linear_log

CFG = {"enabled": "true", "key": "k", "url": "u", "team": "T", "read_team": "R", "project": "P", "report_base": ""}


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def make_run(root: Path, *, kind: str = "ticket") -> Path:
    folder = root / "run"
    write(folder / "summary.json", {"verdict": "NEEDS_REVISION", "seconds": 600, "cost": 1.5,
                                    "tests": {"passed": 5, "failed": 1, "flaky": 0}, "e2e": "NEEDS_REVISION  passed 9", "ux": "PASS  score 90"})
    write(folder / "ux-report.html", "<html></html>")
    write(folder / "bugs.json", {"bugs": [{"title": "A: broken", "severity": "High", "priority": "P1"}]})
    write(folder / "bugs.md", "## A: broken\n\nBody ![x](bug-evidence/a.png)\n")
    write(folder / "bug-evidence" / "a.png", "png")
    write(folder / "e2e" / "bugs.json", {"bugs": [{"title": "Docs: empty name accepted", "severity": "Medium", "priority": "P2"}]})
    write(folder / "e2e" / "bugs.md", "## Docs: empty name accepted\n\nBody\n")
    return folder


class FakeLinear:
    """Answers the few queries linear_log makes. `existing` maps a marker to an issue that already has it."""

    def __init__(self, existing=None):
        self.existing = existing or {}
        self.created = []
        self.comments = []
        self.next = 1100

    def gql(self, cfg, query, variables=None):
        v = variables or {}
        if "team(id" in query:
            return {"team": {"key": "YOR", "labels": {"nodes": [{"id": "l1", "name": "Bug: Functionality"}, {"id": "l2", "name": "automated"}]}}}
        if "issues(first:1" in query:
            hit = next((i for m, i in self.existing.items() if m in v["m"]), None)
            return {"issues": {"nodes": [hit] if hit else []}}
        if "issueCreate" in query:
            self.next += 1
            issue = {"id": f"id{self.next}", "identifier": f"YOR-{self.next}", "url": f"https://l/{self.next}"}
            self.created.append((v["i"], issue))
            return {"issueCreate": {"issue": issue}}
        if "commentCreate" in query:
            self.comments.append(v["i"])
            return {"commentCreate": {"comment": {"url": "https://l/comment"}}}
        raise AssertionError(query)


class LinearLogTest(unittest.TestCase):
    def file(self, fake, folder, **kw):
        manifest = {"id": "LEX-1-20261103T000000Z-abcd", "kind": "ticket", "ticket": "LEX-1", "pr": 7, "trigger": "pr"}
        with mock.patch.object(linear_log, "config", return_value=CFG), \
             mock.patch.object(linear_log, "gql", fake.gql), \
             mock.patch.object(linear_log, "upload", lambda cfg, f: f"https://uploads/{f.name}"):
            return linear_log.file_run(folder, "tickets/LEX-1/x", manifest, 2, 3, **kw)

    def test_new_run_makes_tracking_ticket_bugs_and_one_comment(self):
        with tempfile.TemporaryDirectory() as raw:
            fake = FakeLinear()
            result = self.file(fake, make_run(Path(raw)))
            titles = [c[0]["title"] for c in fake.created]
            self.assertEqual(titles[0], "QA: LEX-1")
            self.assertIn("A: broken", titles)
            self.assertIn("[E2E] Docs: empty name accepted", titles)
            bug = next(c[0] for c in fake.created if c[0]["title"] == "A: broken")
            self.assertEqual(bug["priority"], 2)
            self.assertEqual(bug["labelIds"], ["l1", "l2"])
            self.assertIn("https://uploads/a.png", bug["description"])  # screenshot is hosted by Linear
            self.assertIn("qx-bug:", bug["description"])
            body = fake.comments[0]["body"]
            self.assertIn("run 2 of 3", body)
            self.assertIn("Feature bugs (1)", body)
            self.assertIn("E2E regression bugs (1)", body)
            self.assertIn("https://uploads/ux-report.html", body)
            self.assertEqual(len(fake.comments), 1)
            self.assertTrue((Path(raw) / "run" / "linear-filing.json").is_file())
            self.assertEqual(result["ticket"]["identifier"], "YOR-1101")

    def test_open_bug_gets_a_seen_again_comment_not_a_second_ticket(self):
        with tempfile.TemporaryDirectory() as raw:
            fp = linear_log.fingerprint("e2e", "LEX-1", "Docs: empty name accepted")
            old = {"id": "old", "identifier": "YOR-900", "url": "u", "state": {"type": "started"},
                   "comments": {"nodes": [{"body": linear_log.SEEN_MARK}]}}
            fake = FakeLinear({f"qx-bug:{fp}": old})
            result = self.file(fake, make_run(Path(raw)))
            self.assertNotIn("[E2E] Docs: empty name accepted", [c[0]["title"] for c in fake.created])
            self.assertIn("occurrence 3", fake.comments[0]["body"])
            self.assertEqual(result["e2e_bugs"][0]["status"], "seen again")
            self.assertEqual(result["e2e_bugs"][0]["identifier"], "YOR-900")

    def test_closed_bug_is_filed_again_and_points_at_the_old_one(self):
        with tempfile.TemporaryDirectory() as raw:
            fp = linear_log.fingerprint("feature", "LEX-1", "A: broken")
            old = {"id": "old", "identifier": "YOR-5", "url": "u", "state": {"type": "completed"}, "comments": {"nodes": []}}
            fake = FakeLinear({f"qx-bug:{fp}": old})
            self.file(fake, make_run(Path(raw)))
            bug = next(c[0] for c in fake.created if c[0]["title"] == "A: broken")
            self.assertIn("Previously filed as YOR-5", bug["description"])

    def test_a_run_is_filed_once_unless_forced(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = make_run(Path(raw))
            first = FakeLinear()
            self.file(first, folder)
            second = FakeLinear()
            self.file(second, folder)
            self.assertEqual(second.created, [])
            self.file(second, folder, force=True)
            self.assertTrue(second.created)

    def test_refuses_the_read_team(self):
        with self.assertRaises(linear_log.LinearError):
            linear_log.check_config({**CFG, "team": "R"})

    def test_fingerprints(self):
        a = linear_log.fingerprint("e2e", "LEX-1", "Docs:  Empty name")
        self.assertEqual(a, linear_log.fingerprint("e2e", "LEX-9", "docs: empty name"))  # E2E bugs are global
        self.assertNotEqual(linear_log.fingerprint("feature", "LEX-1", "x"), linear_log.fingerprint("feature", "LEX-2", "x"))

    def test_attempt_counts_runs_of_the_same_ticket(self):
        rows = [{"id": "a", "kind": "ticket", "ticket": "LEX-1", "createdAt": "2026-11-01"},
                {"id": "b", "kind": "ticket", "ticket": "LEX-1", "createdAt": "2026-11-02"},
                {"id": "c", "kind": "ticket", "ticket": "LEX-2", "createdAt": "2026-11-01"}]
        self.assertEqual(linear_log.attempt_of(rows[1], rows), (2, 2))
        self.assertEqual(linear_log.attempt_of(rows[2], rows), (1, 1))

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {"QA_LINEAR_LOG": ""}):
            self.assertFalse(linear_log.is_enabled({**CFG, "enabled": ""}))


if __name__ == "__main__":
    unittest.main()
