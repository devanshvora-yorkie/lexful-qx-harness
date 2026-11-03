"""Run one trigger without the server, then exit: the entry point for a container started per UAT deploy.

    python -m app.cli --sha <deployed sha> [--pr 1924] [--ticket LEX-3700]   what a UAT deploy sends
    python -m app.cli --ticket LEX-3700                                      one ticket
    python -m app.cli --e2e                                                  E2E User Journey TCs only

The run is the same one the server would queue: preflight, the E2E stage, the ticket's tests, the
UX audit and the report. Its folder is written under QA_RUNS_DIR (mount runs/ to keep it), and run.log
is printed as it grows. Nothing is written to Linear or GitHub.

Exit status: 0 PERFECT, 1 NEEDS_REVISION, 2 HALTED or failed, 64 bad arguments. When GITHUB_OUTPUT is
set (a GitHub Actions step), `run_dir`, `verdict` and `report` are appended to it for later steps.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from app import store
from app.logbook import echo_run
from app.pipeline import create_triggered_run, execute_run

EXIT = {"PERFECT": 0, "NEEDS_REVISION": 1}


def _ticket(value: str) -> str:
    key = value.strip().upper()
    prefix, _dash, number = key.partition("-")
    if prefix != "LEX" or not number.isdigit():
        raise argparse.ArgumentTypeError("a ticket looks like LEX-1234")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Run one QA trigger and exit.")
    parser.add_argument("--ticket", type=_ticket, help="Linear ticket, LEX-1234")
    parser.add_argument("--pr", type=int, help="pull request number")
    parser.add_argument("--sha", help="the commit the UAT deployment shipped")
    parser.add_argument("--e2e", action="store_true", help="run only the E2E User Journey TCs")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return 0 if stop.code == 0 else 64
    if args.e2e and (args.ticket or args.pr or args.sha):
        print("--e2e runs the checked-in suite alone; drop --ticket, --pr and --sha", file=sys.stderr)
        return 64
    if not (args.e2e or args.ticket or args.pr or args.sha):
        print("give --sha (a UAT deploy), --ticket, --pr, or --e2e", file=sys.stderr)
        return 64

    if args.e2e:
        row = store.create_run(ticket=None, pr=None, sha=None, kind="phase1", trigger="e2e")
    else:
        trigger = "uat-deploy" if args.sha else "ticket" if args.ticket else "pr"
        row = create_triggered_run(ticket=args.ticket, pr=args.pr, sha=args.sha, trigger=trigger)
    run_id = str(row["id"])
    echo_run(store.run_dir(run_id))
    store.update_run(run_id, status="queued")
    execute_run(run_id)

    final = store.get_run(run_id) or {}
    folder = store.run_dir(run_id)
    try:
        verdict = str(json.loads((folder / "qa-result.json").read_text(encoding="utf-8")).get("verdict") or "HALTED")
    except (OSError, ValueError):
        verdict = "HALTED"
    report = folder / "linear-report.md"
    print(f"\nrun {run_id}  status {final.get('status')}  verdict {verdict}\n  folder {folder}\n  report {report}", flush=True)
    outputs = os.environ.get("GITHUB_OUTPUT")
    if outputs:
        with open(outputs, "a", encoding="utf-8") as handle:
            handle.write(f"run_dir={folder}\nverdict={verdict}\nreport={report}\n")
    return EXIT.get(verdict, 2)


if __name__ == "__main__":
    sys.exit(main())
