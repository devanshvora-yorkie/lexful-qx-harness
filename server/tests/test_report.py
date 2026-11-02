import json
import tempfile
import unittest
from pathlib import Path

from app import bugs, evidence, linear_report, prune
from app.pipeline import apply_verification, verifier_hints


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def results_with_screenshot(folder: Path, title: str) -> None:
    shot = folder / "playwright" / "output" / "case-1" / "test-failed-1.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"png")
    write(folder / "playwright" / "results.json", {"suites": [{"title": "a.spec.ts", "file": "a.spec.ts", "specs": [{
        "title": title, "tests": [{"results": [{"status": "failed", "attachments": [
            {"contentType": "image/png", "path": "/old/path/before/rename/playwright/output/case-1/test-failed-1.png"}]}]}]}]}]})


class EvidenceTest(unittest.TestCase):
    def test_failure_screenshot_is_copied_even_after_the_folder_was_renamed(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            results_with_screenshot(folder, "TC-1 saves the name")
            found = evidence.screenshots_for(folder, "bug:1", {"affectedTests": ["TC-1 saves the name"]})
            self.assertEqual(found, ["bug-evidence/bug-1-failure-1.png"])
            self.assertTrue((folder / found[0]).is_file())

    def test_the_verifier_screenshot_comes_first_and_is_named_by_ref(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "bug-evidence" / "finding-F1.png", "x")
            self.assertEqual(evidence.screenshots_for(folder, "finding:F1", {}), ["bug-evidence/finding-F1.png"])

    def test_a_bug_with_no_screenshot_gets_none(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(evidence.screenshots_for(Path(raw), "bug:1", {"affectedTests": ["x"]}), [])


class BugsJsonTest(unittest.TestCase):
    def test_bugs_md_and_bugs_json_carry_the_screenshot(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            results_with_screenshot(folder, "TC-1 saves the name")
            triage = {"bugs": [{"area": "Docs", "failure": "Save loses the name", "severity": "High",
                                "affectedTests": ["TC-1 saves the name"], "expected": "kept", "actual": "lost",
                                "steps": ["open", "save"], "evidence": ["log"]}],
                      "failures": [{"class": "bug", "title": "TC-1 saves the name"}]}
            self.assertTrue(bugs.publish_bugs(folder, ticket="LEX-1", run_id="r", url="u", build="b",
                                              failed=1, triage=triage, still_failing=[]))
            text = (folder / "bugs.md").read_text()
            self.assertIn("Screenshot: bug-evidence/bug-1-failure-1.png", text)
            record = json.loads((folder / "bugs.json").read_text())["bugs"][0]
            self.assertEqual(record["screenshots"], ["bug-evidence/bug-1-failure-1.png"])
            self.assertEqual(record["severity"], "High")


class VerificationTest(unittest.TestCase):
    def test_a_bug_the_verifier_cannot_reproduce_becomes_spec_work(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            triage = {"failures": [{"class": "bug", "title": "row opens the drawer", "action": "reported"}],
                      "bugs": [{"failure": "seed row missing", "affectedTests": ["row opens the drawer"]}]}
            write(folder / "triage-1.json", triage)
            write(folder / "verify.json", {"results": [{"ref": "bug:1", "reproduced": False,
                                                       "notes": "AAA-SRV-001 is gone", "specFix": "use CCL-SRV-001"}]})
            self.assertEqual(apply_verification(folder), "0 confirmed, 1 not reproduced")
            after = json.loads((folder / "triage-1.json").read_text())
            self.assertEqual(after["bugs"][0]["status"], "skipped")
            self.assertEqual(after["failures"][0]["class"], "spec")
            self.assertEqual(verifier_hints(folder), {"row opens the drawer": "use CCL-SRV-001"})
            self.assertFalse(bugs.publish_bugs(folder, ticket="E2E", run_id="r", url="u", build="b", failed=1,
                                               triage=after, still_failing=[{"title": "row opens the drawer", "file": "a", "error": "x"}]))

    def test_a_reproduced_bug_stays_and_the_others_are_dropped(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "triage-1.json", {"failures": [], "bugs": [{"failure": "a", "severity": "High"}, {"failure": "b"}]})
            write(folder / "verify.json", {"results": [{"ref": "bug:1", "reproduced": True}, {"ref": "bug:2", "reproduced": False}]})
            apply_verification(folder)
            kept = bugs.collect_bugs(json.loads((folder / "triage-1.json").read_text()), [])
            self.assertEqual([b["failure"] for b in kept], ["a"])


class PruneTest(unittest.TestCase):
    def test_a_finished_run_loses_scratch_and_keeps_the_record(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            for name in ("contents.txt", "prompt.md", "heal-1.md", "toolchain.log", "context-pack.json",
                         "explore/snap-a.yml", "explore/pw-cli.json", "opencode/session.json", "opencode/children.json",
                         "playwright/html/data/x.zip", "playwright/output/a/trace.zip"):
                write(folder / name, "x" * 100)
            for name in ("report.md", "bugs.json", "bug-evidence/bug-1.png", "explore/flow.md", "explore/walk1.js",
                         "explore/ux/a.png", "specs/a.spec.ts", "playwright/results.json", "playwright/output/a/test-failed-1.png"):
                write(folder / name, "keep")
            write(folder / "opencode" / "agent.jsonl", "line\n" * 500)
            freed = prune.prune_run(folder)
            self.assertGreater(freed, 0)
            for gone in ("contents.txt", "prompt.md", "heal-1.md", "toolchain.log", "context-pack.json", "explore/snap-a.yml",
                         "opencode/session.json", "playwright/html", "playwright/output/a/trace.zip", "opencode/agent.jsonl"):
                self.assertFalse((folder / gone).exists(), gone)
            for kept in ("report.md", "bugs.json", "bug-evidence/bug-1.png", "explore/flow.md", "explore/walk1.js",
                         "explore/ux/a.png", "specs/a.spec.ts", "playwright/results.json",
                         "playwright/output/a/test-failed-1.png", "opencode/agent.jsonl.gz"):
                self.assertTrue((folder / kept).exists(), kept)

    def test_a_failed_run_keeps_everything_but_playwrights_heavy_output(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "prompt.md", "x")
            write(folder / "context-pack.json", "x")
            write(folder / "playwright" / "html" / "index.html", "x")
            prune.prune_run(folder, finished=False)
            self.assertTrue((folder / "prompt.md").exists())
            self.assertTrue((folder / "context-pack.json").exists())
            self.assertFalse((folder / "playwright" / "html").exists())


class LinearReportTest(unittest.TestCase):
    def test_the_report_joins_e2e_feature_and_ux(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "qa-result.json", {"verdict": "PERFECT", "test_results": {"passed": 4, "failed": 0, "skipped": 0}})
            write(folder / "bugs.json", {"bugs": [{"title": "Docs — Save loses the name — LEX-1", "severity": "High", "priority": "P1",
                                                   "steps": ["open", "save"], "expected": "kept", "actual": "lost",
                                                   "screenshots": ["bug-evidence/bug-1.png"], "confidence": "confirmed"}]})
            write(folder / "e2e" / "qa-result.json", {"verdict": "NEEDS_REVISION", "test_results": {"passed": 60, "failed": 2}, "open_issues": ["bug: x"]})
            write(folder / "e2e" / "triage-1.json", {"failures": [{"class": "spec", "action": "patched", "title": "row opens", "reason": "seed renamed"}]})
            write(folder / "e2e" / "bugs.json", {"bugs": []})
            write(folder / "ux-scorecard.json", {"verdict": "PASS WITH ADVISORIES", "score": 90, "counts": {"S2": 1}})
            write(folder / "ux-findings.json", [{"severity": "S2", "title": "Label missing", "checkId": "A11Y-03", "screenshot": "explore/ux/a.png"}])
            write(folder / "ux-report.html", "<html/>")
            write(folder / "bug-evidence" / "bug-1.png", "x")
            text = linear_report.build(folder, {"id": "r", "ticket": "LEX-1"}, verdict="PERFECT", issues=[])
            for part in ("# LEX-1: QA report", "## 1. E2E User Journey TCs", "60 passed, 2 failed", "Updated in place because the app changed: **1**",
                         "## 2. Feature Specific TCs", "![bug-1](bug-evidence/bug-1.png)", "## 3. UI/UX audit", "| S2 | Label missing |",
                         "`ux-report.html`", "`bug-evidence/` (1 screenshot(s))"):
                self.assertIn(part, text)


if __name__ == "__main__":
    unittest.main()
