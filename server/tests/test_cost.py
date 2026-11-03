import json
import tempfile
import unittest
from pathlib import Path

from app.pipeline import phase_costs


def step(output, read, cost):
    return json.dumps({"part": {"type": "step-finish", "cost": cost, "tokens": {"output": output, "cache": {"read": read}}}})


class CostTest(unittest.TestCase):
    def test_phases_are_summed_from_the_opencode_logs(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            logs = folder / "opencode"
            logs.mkdir()
            (logs / "agent.jsonl").write_text(step(100, 1000, 0.5) + "\n" + step(50, 2000, 0.25) + "\nnot json\n")
            (logs / "heal-1.jsonl").write_text(step(10, 500, 0.1) + "\n")
            (logs / "heal-2.jsonl").write_text(step(10, 500, 0.1) + "\n")
            (logs / "ux-audit.jsonl").write_text(step(20, 100, 0.05) + "\n")
            phases = phase_costs(folder)
            self.assertEqual(phases["Explore + Author"], {"steps": 2, "output": 150, "cacheRead": 3000, "cost": 0.75})
            self.assertEqual(phases["Heal"]["steps"], 2)
            self.assertEqual(phases["UX audit"]["steps"], 1)

    def test_the_e2e_stage_of_a_ticket_run_is_counted_apart(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "opencode").mkdir()
            (folder / "opencode" / "heal-1.jsonl").write_text(step(10, 0, 0.2) + "\n")
            (folder / "e2e" / "opencode").mkdir(parents=True)
            (folder / "e2e" / "opencode" / "heal-1.jsonl").write_text(step(10, 0, 0.3) + "\n")
            phases = phase_costs(folder)
            self.assertEqual(phases["Heal"]["cost"], 0.2)
            self.assertEqual(phases["E2E Heal"]["cost"], 0.3)

    def test_no_logs_no_phases(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(phase_costs(Path(raw)), {})


if __name__ == "__main__":
    unittest.main()
