# Logging a run to Linear

When `QA_LINEAR_LOG=true`, the last step of every finished run writes the result to Linear: one **tracking ticket** per source ticket, one **comment** per run, and one **Bug ticket** per bug. It is off by default.

This is server code (`server/app/linear_log.py`), not an agent session. The agent never gets Linear write access, and filing needs no model: the bug text is already written in `bugs.md`, the numbers are in `summary.json`, and the links are known. It costs no tokens.

## What you see in Linear

```text
YOR-1101  QA: LEX-2293                       tracking ticket, reused by every run of LEX-2293
  comment   QA run LEX-2293-20261103T143623Z-3aab, NEEDS_REVISION, run 1 of 1 ...
  comment   QA run LEX-2293-20261105T091200Z-77c1, PERFECT,        run 2 of 2 ...
  YOR-1102  PATCH and DELETE ...: Changing or removing a link ...    feature bug (sub-issue)
  YOR-1103  [E2E] Documents: create drawer ...                       E2E regression bug (sub-issue)
```

**The tracking ticket.** Created on the first run of a source ticket and found again by a hidden marker in its description. It links to the source ticket (`LEX-2293`). The harness does not write to the source ticket, because the Linear key may only create in the write team.

**The comment, one per run.** It carries the run id, the verdict, `run N of M` for this ticket, the feature test counts, the E2E result, the UX verdict and score, time and cost, the bugs with links, and the UX report link.

**Bug tickets.** The text is `bugs.md` as written for the run: what happens, environment, steps, expected, actual, root cause, evidence. Screenshots are uploaded to Linear so they show in the ticket. Labels are `Bug: Functionality` and `automated`. Priority follows the bug (P0 urgent to P3 low).

## E2E bugs

A ticket run has two sets of bugs, and the comment keeps them apart:

| Section in the comment | Where it comes from | In Linear |
|---|---|---|
| Feature bugs | the ticket's own tests, `bugs.json` of the run | title as written |
| E2E regression bugs | the E2E User Journey stage, `e2e/bugs.json` | title starts with `[E2E]` |

An E2E bug is a regression in the core journeys (search, asset CRUD, document editing). It is not necessarily caused by the ticket under test, so it is reported as its own list and is easy to filter (`[E2E]` in the title).

E2E bugs repeat: the same failing case shows up on every deploy until someone fixes it. So the harness does not file it again each time (see below). A run started on its own (`npm run e2e`, `/run/phase1`) logs to one standing ticket, `QA: E2E User Journey TCs (UAT regression)`.

## Who keeps which counter

| Number | Owner | Notes |
|---|---|---|
| Issue number (`YOR-1102`) | Linear | Assigned by Linear when the issue is created. The harness never sets or predicts it. |
| Run id (`LEX-2293-20261103T143623Z-3aab`) | the harness | Written at the start of the run and kept in the folder name, `manifest.json` and every comment. |
| Run N of M for a ticket | the harness | Counted from the harness's own `runs/index.json`, so it only counts runs this harness has made. |
| Occurrence count of a bug | the harness | Counted from "seen again" comments on the bug's Linear ticket. |

**Not filing the same bug twice.** Every bug gets a fingerprint (a short hash of its title, scoped to the source ticket for feature bugs and global for E2E bugs). The fingerprint is written into the bug's description as a hidden marker. Before creating a bug, the harness searches the project for that marker:

- Found and still open: no new ticket. A comment `Seen again in run ... (occurrence 3)` is added to the existing one, and the run comment lists it as `seen again`.
- Found and done: a new ticket is created that points to the closed one, because the bug has come back.
- Found and canceled: not filed again. Cancel a ticket in Linear to tell the harness it is not a bug; the run comment lists it as `closed as not a bug`.
- Not found: a new ticket.

The search is done in Linear, so it still works if `runs/` is wiped or the harness runs on another machine.

## Where the UX report is viewed

Linear cannot render an HTML file. There are two options:

1. **Upload to Linear (the default).** `ux-report.html` is stored in Linear and the comment links to it. Only people signed in to the workspace can open it, and the browser **downloads** it instead of showing it, so the reader opens the file locally.
2. **Host it.** Serve the `runs/` folder behind your VPN, SSO or a private bucket and set `QA_REPORT_BASE_URL=https://qa.example.internal/runs`. The comment then links to `<base>/<run folder>/ux-report.html`, which opens in the browser. This is what we recommend for daily use.

GitHub is not involved: nothing is pushed to the repository.

## Safety rules

- It writes only to `LINEAR_WRITE_TEAM_ID` and `LINEAR_WRITE_PROJECT_ID`. It stops if that team is the read team (`LINEAR_READ_TEAM_ID`) or if the team key is `LEX`.
- It runs only for runs that ended `completed` or `needs_revision`. A halted, failed or cancelled run is not logged; the run log says so.
- A Linear error never fails a run. The run log gets a `linear` line with the reason, and the run can be filed later.
- A run is filed once. `linear-filing.json` in the run folder records what was created; filing again needs `--force`.

## Set up and test

1. In `.env`, set `LINEAR_API_KEY`, `LINEAR_WRITE_TEAM_ID`, `LINEAR_WRITE_PROJECT_ID`, and `QA_LINEAR_LOG=true`. Optionally set `QA_REPORT_BASE_URL`.
2. Restart: `docker compose up -d --force-recreate harness`.
3. To log a run that already finished, without running anything again:

```bash
docker compose exec harness server/.venv/bin/python -m app.linear_log <run id>
docker compose exec harness server/.venv/bin/python -m app.linear_log <run id> --force   # file it again
```

Run it twice with `--force` to see the de-duplication: the second pass creates no new bug tickets and comments `Seen again ... (occurrence 2)` on the open ones.

The unit tests (no network) are `server/tests/test_linear_log.py`.
