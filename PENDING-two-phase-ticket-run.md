# Pending: one ticket run, two suites

Status: not started. Discussion only. No code changes yet.

A ticket trigger becomes one run. E2E User Journey TCs run first. Feature Specific TCs are written only for what that suite does not already cover, then a few of them are promoted back into `e2e test cases`.

## E2E User Journey TCs

1. Preflight signs in against live UAT.
2. Run every spec in `e2e test cases` (about 60 today).
3. Heal locator drift in those files, up to 3 heals. The server re-runs only when a spec file changed.
4. Log what remains:
   - **healed** — renamed locator, strict-mode match, or a wait that expired while the control was already on the page.
   - **bug** — product did the wrong thing, with evidence from the last attempt.
   - **flake** — empty page, `goto` timeout, or a failure that passed on retry. Do not call this a bug.
5. A remaining bug does not stop Feature Specific TCs. Today’s regression (`regression-20261023T114747Z-f35a`) finished 57 passed and 2 failed, and several “bugs” were flakes.

This suite does not write new tests and does not call Linear for the suite itself.

## Feature Specific TCs

1. Full preflight for the ticket: Linear, GitHub, context pack.
2. Read every spec already in `e2e test cases`, including ones that failed as bugs. A failing test is still coverage. Skipping only the last green run would rewrite the same cases.
3. From the ticket and the pull request, write at most three journeys:
   - happy path that proves the user-visible change
   - the guard the change must enforce (skip if the ticket has none)
   - read-back: do the change, reload, assert the value stuck
4. Run only those new specs against UAT and heal them in the run folder.
5. Promote into `e2e test cases` only when the test passed on the final UAT run, the assertion is not already covered, it maps to one of those journeys, and it creates and cleans up its own data.
6. Put the file in the matching suite folder (`asset crud`, `document editing`, `search`, or a new folder). Record the ticket id in that suite’s `FEATURE.md`.

Cap promotions at 1–3 per ticket. A failed, skipped, or weakened test stays in `runs/<ticket>/<run-id>/` and is not appended.

## Access

`e2e test cases` is already mounted into the container and `qa-author` can read it. The gap is the instruction: a ticket run is not told to compare new specs with that folder. Reading happens while planning. Writing back into the folder is the promotion step, after the new test has passed.

## Conflicts with the current skill

The author skill still says at least 15 tests and every listing action. That has to change or the three-journey cap will lose. Ticket specs are written under `runs/<ticket>/<run-id>/specs/` today and are not copied into `e2e test cases`. The checked-in suite and the ticket are still two queue items; this plan makes them one run.
