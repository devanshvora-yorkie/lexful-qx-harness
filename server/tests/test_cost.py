import json
import tempfile
import unittest
from pathlib import Path

from app.pipeline import _cost_section, phase_costs


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
            text = "\n".join(_cost_section(folder))
            self.assertIn("| UX audit | 1 |", text)
            self.assertIn("**$1.00**", text)
            self.assertTrue((folder / "cost.json").is_file())

    def test_no_logs_no_section(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(_cost_section(Path(raw)), [])


if __name__ == "__main__":
    unittest.main()
