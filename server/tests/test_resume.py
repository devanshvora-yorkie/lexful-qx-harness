import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app.pipeline import _handoff_written


class HandoffTest(unittest.TestCase):
    def test_a_handoff_written_during_the_run_counts(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            started = time.time() - 5
            (folder / "planned-specs.json").write_text("{}")
            with mock.patch("app.pipeline.runners.planned_specs", return_value=["specs/a.spec.ts"]):
                self.assertTrue(_handoff_written(folder, started))

    def test_a_handoff_from_an_earlier_run_does_not_count(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "planned-specs.json").write_text("{}")
            with mock.patch("app.pipeline.runners.planned_specs", return_value=["specs/a.spec.ts"]):
                self.assertFalse(_handoff_written(folder, time.time() + 60))

    def test_no_plan_or_no_runnable_spec_is_not_a_handoff(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.assertFalse(_handoff_written(folder, 0.0))
            (folder / "planned-specs.json").write_text("{}")
            with mock.patch("app.pipeline.runners.planned_specs", return_value=[]):
                self.assertFalse(_handoff_written(folder, 0.0))


if __name__ == "__main__":
    unittest.main()
