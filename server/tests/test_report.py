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
                                              failed=1, triage=triage))
            text = (folder / "bugs.md").read_text()
            self.assertIn("![bug-1-failure-1.png](bug-evidence/bug-1-failure-1.png)", text)
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
                                               triage=after))

    def test_the_verifier_s_steps_replace_the_written_ones(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "api-findings.json", {"findings": [{"id": "F1", "steps": ["guessed"], "expected": "e", "actual": "a", "evidence": "x"}]})
            write(folder / "verify.json", {"results": [{"ref": "finding:F1", "reproduced": True, "persona": "viewer",
                                                       "steps": ["Open /docs as viewer", "Click New"]}]})
            apply_verification(folder)
            finding = json.loads((folder / "api-findings.json").read_text())["findings"][0]
            self.assertEqual(finding["steps"], ["Open /docs as viewer", "Click New"])
            self.assertEqual((finding["persona"], finding["confidence"]), ("viewer", "confirmed"))

    def test_a_reproduced_bug_stays_and_the_others_are_dropped(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "triage-1.json", {"failures": [], "bugs": [{"failure": "a", "severity": "High"}, {"failure": "b"}]})
            write(folder / "verify.json", {"results": [{"ref": "bug:1", "reproduced": True}, {"ref": "bug:2", "reproduced": False}]})
            apply_verification(folder)
            kept = bugs.collect_bugs(json.loads((folder / "triage-1.json").read_text()))
            self.assertEqual([b["failure"] for b in kept], ["a"])


class PruneTest(unittest.TestCase):
    def test_a_finished_run_keeps_only_the_record(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            scratch = (
                "contents.txt", "prompt.md", "heal-1.md", "affected-heal-1.md", "toolchain.log", "context-pack.json",
                "api-probes.jsonl", "ux-audit.log", "e2e-coverage.md", "planned-specs.json", "report.html", "report.md",
                "explore/snap-a.yml", "explore/pw-cli.json", "opencode/session.json", "opencode/children.json",
                "playwright/html/data/x.zip", "playwright/output/a/trace.zip", "playwright/output/a/test-failed-1.png",
                "playwright/results.json", "playwright/output.log", "playwright/signals.jsonl",
                "affected/playwright/results.json", "e2e/run.log", "e2e/report.md", "e2e/source.txt",
                "e2e/opencode/heal-1.jsonl", "e2e/playwright/results.json", "e2e/playwright/output/b/test-failed-1.png",
            )
            record = (
                "linear-report.md", "linear-report.html", "ux-report.html", "bugs.json", "bugs.md", "bug-evidence/bug-1.png",
                "explore/flow.md", "explore/walk1.js", "explore/ux/a.png", "specs/a.spec.ts", "coverage.json",
                "playwright/test-outcomes.json", "triage-1.json", "verify.json", "affected/test-outcomes.json",
                "affected/triage.json", "e2e/qa-result.json", "e2e/playwright/test-outcomes.json", "e2e/triage-2.json",
                "e2e/bugs.json", "e2e/bugs.md", "e2e/bug-evidence/bug-1.png",
            )
            for name in scratch:
                write(folder / name, "x" * 100)
            for name in record:
                write(folder / name, "keep")
            for name in ("agent", "heal-1", "verify-1", "agent-plan", "promote", "ux-audit", "affected-heal-1"):
                write(folder / "opencode" / f"{name}.jsonl", "line\n" * 500)
            self.assertGreater(prune.prune_run(folder), 0)
            for gone in scratch:
                self.assertFalse((folder / gone).exists(), gone)
            for kept in record:
                self.assertTrue((folder / kept).exists(), kept)
            transcripts = sorted(path.name for path in (folder / "opencode").iterdir())
            self.assertEqual(transcripts, ["agent.jsonl.gz", "heal-1.jsonl.gz", "verify-1.jsonl.gz"])

    def test_an_old_run_without_the_one_report_keeps_report_md(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "report.md", "# old")
            prune.prune_run(folder)
            self.assertTrue((folder / "report.md").exists())

    def test_a_failed_run_keeps_everything_but_playwrights_heavy_output(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "prompt.md", "x")
            write(folder / "context-pack.json", "x")
            write(folder / "playwright" / "results.json", "x")
            write(folder / "playwright" / "html" / "index.html", "x")
            write(folder / "e2e" / "playwright" / "output" / "a" / "video.webm", "x")
            prune.prune_run(folder, finished=False)
            self.assertTrue((folder / "prompt.md").exists())
            self.assertTrue((folder / "context-pack.json").exists())
            self.assertTrue((folder / "playwright" / "results.json").exists())
            self.assertFalse((folder / "playwright" / "html").exists())
            self.assertFalse((folder / "e2e" / "playwright" / "output" / "a" / "video.webm").exists())


def outcome(title: str, status: str, *tags: str) -> dict:
    return {"file": "a.spec.ts", "title": title, "status": status, "tags": list(tags)}


class LinearReportTest(unittest.TestCase):
    def test_the_report_joins_e2e_feature_and_ux(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "qa-result.json", {"verdict": "PERFECT", "test_results": {"passed": 4, "failed": 0, "skipped": 0}})
            write(folder / "bugs.json", {"bugs": [{"title": "Docs: Save loses the name", "severity": "High", "priority": "P1",
                                                   "steps": ["open", "save"], "expected": "kept", "actual": "lost",
                                                   "screenshots": ["bug-evidence/bug-1.png"], "confidence": "confirmed",
                                                   "ticket": "LEX-1", "affectedTests": ["TC-LEX-1-002"]}]})
            write(folder / "promoted.json", {"cases": [{"id": "AC-040", "title": "x"}], "skipped": [{"title": "TC-LEX-1-001", "reason": "API only"}]})
            write(folder / "e2e" / "qa-result.json", {"verdict": "NEEDS_REVISION", "test_results": {"passed": 60, "failed": 2},
                                                      "open_issues": ["bug: \u001b[31mx\u001b[39m"]})
            write(folder / "e2e" / "triage-1.json", {"failures": [{"class": "spec", "action": "patched", "title": "row opens", "reason": "seed renamed"}]})
            write(folder / "e2e" / "bugs.json", {"bugs": []})
            write(folder / "ux-scorecard.json", {"verdict": "PASS WITH ADVISORIES", "score": 90, "counts": {"S2": 1}})
            write(folder / "ux-findings.json", [{"severity": "S2", "title": "Label missing", "checkId": "A11Y-03",
                                                 "screenshot": "explore/ux/a.png", "solution": "What to fix (plain English): name the field."}])
            write(folder / "ux-report.html", "<html/>")
            write(folder / "bug-evidence" / "bug-1.png", "x")
            text = linear_report.build(folder, {"id": "r", "ticket": "LEX-1"}, verdict="PERFECT", issues=[])
            for part in ("# LEX-1: QA report", "## 1. E2E User Journey TCs", "| 62 | 60 | 2 | 0 | 97% |",
                         "Test cases added to the E2E suite by this run: 1 (1 candidates not added)",
                         "Updated in place because the app changed: 1", "- bug: x", "## 2. Feature Specific TCs",
                         "#### 1. Docs: Save loses the name", "Found by: LEX-1 (TC-LEX-1-002)", "1. open", "- Expected: kept",
                         "[bug-1.png](bug-evidence/bug-1.png)", "## 3. Suggested UX changes", "| S2 | Label missing | Name the field. |",
                         "[This report in a browser](linear-report.html)", "[UI/UX audit, interactive](ux-report.html)"):
                self.assertIn(part, text)
            self.assertNotIn("\u001b", text)

    def test_type_and_suite_come_from_the_tags_playwright_recorded(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "qa-result.json", {"verdict": "NEEDS_REVISION", "test_results": {"passed": 1, "failed": 1}})
            write(folder / "context-pack.json", {"pullRequests": [{"number": 9, "merged": True}]})
            write(folder / "playwright" / "test-outcomes.json", [
                outcome("TC-LEX-9-001: one", "passed", "@positive", "@smoke"),
                outcome("TC-LEX-9-002: two", "failed", "@edge", "@regression"),
            ])
            text = linear_report.build(folder, {"id": "r", "ticket": "LEX-9", "pr": 9, "trigger": "uat-deploy", "sha": "abcdef1234567"},
                                       verdict="NEEDS_REVISION", issues=[])
            for part in ("| Trigger | UAT deployment |", "| Ticket | LEX-9 |", "| Pull request | #9 (merged) |",
                         "| Deployed commit | `abcdef123456` |", "| 2 | 1 | 1 | 0 | 50% |", "| Positive | 1 | 1 | 0 | 100% |",
                         "| Edge | 1 | 0 | 1 | 0% |", "| BVT | 0 | 0 | 0 | n/a |", "| Smoke | 1 | 1 | 0 | 100% |",
                         "| Regression | 1 | 0 | 1 | 0% |"):
                self.assertIn(part, text)
            self.assertNotIn("Untagged", text)

    def test_a_standalone_e2e_run_reports_only_the_suite(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "qa-result.json", {"verdict": "PERFECT", "test_results": {"passed": 3, "failed": 0}})
            text = linear_report.build(folder, {"id": "regression-1", "kind": "phase1", "trigger": "e2e"}, verdict="PERFECT", issues=[])
            self.assertIn("# E2E User Journey TCs: QA report", text)
            self.assertIn("| Trigger | E2E User Journey TCs, started on their own |", text)
            self.assertIn("| E2E User Journey TCs | 3 | 3 | 0 | 100% | 0 |", text)
            self.assertNotIn("Feature Specific", text)

    def test_the_html_carries_the_same_sections_and_links(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            write(folder / "qa-result.json", {"verdict": "PERFECT", "test_results": {"passed": 1}})
            write(folder / "playwright" / "test-outcomes.json", [outcome("TC-1: a", "passed", "@positive", "@bvt")])
            written = linear_report.write(folder, {"id": "r", "ticket": "LEX-1"}, verdict="PERFECT", issues=[])
            self.assertEqual(written.name, "linear-report.md")
            page = (folder / "linear-report.html").read_text(encoding="utf-8")
            self.assertIn("<h2>2. Feature Specific TCs</h2>", page)
            self.assertIn("<details><summary>All 1 feature TCs</summary>", page)
            self.assertIn('<a href="linear-report.html">This report in a browser</a>', page)
            self.assertNotIn("<details>", written.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
