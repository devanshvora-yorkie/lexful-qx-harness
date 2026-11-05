# Lexful QX Harness: Architecture and Roadmap

This document explains what the harness is, how it is built, what it can do today, and where it goes next. It is written so that someone who has not touched the system for a while can recall how it works. The commands, settings and file layout are in the [README](../README.md) and [run-reference.md](run-reference.md).

## 1. What it is

The QX Harness is an autonomous system that runs **end-to-end QA, feature-specific QA and UI/UX audits** on builds deployed to UAT.

It does not leave the language model to work out what to do. It gives the model **structured crawling and retrieval paths** that say where to look, which tools to call and how much context to gather. Because of that, it runs on small, cheap models. Today every phase runs on one model (Haiku 5.5 on Bedrock), and the model is a setting, so Sonnet or any other capable model can replace it.

**What triggers it**

- a tagged **Linear ticket**, or
- a **pull request deployed from the docu-stack repository**.

**What it produces**

- a verdict (`PERFECT`, `NEEDS_REVISION` or `HALTED`),
- test results with evidence,
- reproducible bug reports,
- a UI/UX audit report,
- one consolidated report per run.

## 2. Context gathering

Before any testing, the harness builds the context the model needs. It does this with fixed retrieval paths, not by letting the model search freely.

- **Ticket context.** The full ticket, its comments, its images and the pull requests that mention it are saved with the run. A short index file points to them, so the model reads the index first and opens the detail only when needed.
- **Code context.** The product repo is fetched read-only at the exact commit running on UAT. The model reads the **git diff** of the pull request and the **neighbouring worktrees** around the changed code, so it sees what changed and what the change might affect.
- **Bounded extra lookups.** If the ticket or PR refers to other tickets or PRs, the model can follow them one hop, within a per-run budget.
- **Right-sized depth.** A small change gets a light pass. A large, cross-cutting feature gets deeper retrieval. The ticket's requirements and the complexity of the change set the depth.
- **Deploy check.** Preflight confirms the merged PR is actually on UAT before any test runs, so we never test a build that does not contain the change.

## 3. The two phases

### Phase 1: E2E regression (every UAT deployment)

A checked-in suite of predefined test cases built around the **three core user journeys**:

1. **Search**
2. **Asset CRUD**
3. **Document editing**

Each journey includes **positive, negative and edge cases**. Their job is to confirm that no deployment breaks the basic functionality of UAT. This phase runs **first** on every deployment (and can also run on its own).

**Self-healing.** UI changes often break tests while the product still works. When a case fails because of locator or spec drift, the harness hands it to a dedicated **E2E self-healer** phase. The healer decides whether the failure is drift in the test or a real product regression:

- **Drift:** the case is repaired in place and the edit is written to a change log, so every repair can be reviewed.
- **Regression:** it is filed as a product bug.

This keeps the suite trustworthy without constant manual maintenance.

### Phase 2: Feature-specific run (ticket and PR driven)

After the baseline, the harness tests the change from the ticket or PR. It explores the feature in the live app, writes new specs, runs them, heals them, audits the UX and files verified bugs. Section 5 describes this in detail.

## 4. One agent, many skills

The harness uses **one agent on one model**. It handles every phase in a **separate session**, and the server tells each session which phase it is in. Each phase has its own skill and task instructions, plus a small set of shared rules. A session reads only its own phase file.

This design has three benefits:

- **Small context.** Nothing is loaded until it is needed, so sessions are cheaper, faster and more accurate.
- **Works on small models.** Each session has one narrow job.
- **Easy to maintain.** Changing one phase does not touch the others.

The agent cannot start subagents, and sessions run one at a time.

| Task | What it does |
|---|---|
| **Preflight and context** | Signs in to UAT, saves the ticket, comments, images and PRs, fetches the code at the deployed commit, and checks the PR is on UAT |
| **E2E run and heal** | Runs the regression suite and repairs drifted cases |
| **Explore** | Maps the change and walks the feature in the live app |
| **Author** | Writes specs for each new behaviour, positive, negative and edge |
| **Run and heal** | Runs the new specs and repairs failures that come from the test, not the product |
| **UX audit** | Audits the journey and writes the UX report |
| **Verify** | Reproduces each suspected bug in a fresh session before it is filed |
| **Promote** | Optionally adds a small number of passing journeys to the permanent suite |
| **Seal and report** | Writes the reports, records the run and prunes scratch files |

## 5. The feature run in detail

1. **Explore first.** The agent does not write tests blind. It acts as an explorer and moves through UAT to the feature using **snapshot trails**: recorded sequences of page-state snapshots and the steps between them. A trail is a verified route to the feature. It records what to click, which states to pass through, and what each screen looked like.
2. **Author.** From the requirements, the diff and what the explorer saw, the agent writes Playwright specs. Each spec step is written only after the agent has done that step in the real app, so specs are grounded in the real UI and not in guesses from the code. Every test carries a type tag (positive, negative or edge) and a suite tag (BVT, smoke, sanity or regression).
3. **Run and heal.** The new specs run on UAT. A failure goes to a fresh healing session, up to three times. Each heal re-runs only the tests that have not passed yet, and a final pass runs every spec in a folder a heal edited. A failure counts as a product bug only once the test itself is sound.
4. **Verify and log bugs.** Suspected bugs are replayed by a fresh session that follows the recorded steps. **Only a bug that is reproduced is written up.** Each bug report is formatted like a ticket, with steps to reproduce, expected versus actual behaviour and a screenshot. A case the walk never reached is recorded as a **gap**, not a bug.
5. **Promote.** At most two passing journeys may be added to the permanent suite. The default is none, so the suite does not grow without control.

## 6. The UX audit

The UX audit **reuses the explorer's trails**. It does not rediscover screens, so it avoids repeat navigation and saves tokens. It audits the journey beside the functional run, and at each screen and state it checks things such as:

- layout, hierarchy and visual consistency,
- interaction states (empty, loading, error, success),
- accessibility basics (contrast, labels, keyboard flow),
- copy clarity and error messages,
- consistency with existing product patterns and the design system.

The audit works against a defined UX rulebook and pattern library, and its checks come from a rule set instead of the model's taste. The agent writes structured findings and a scorecard. **The server then renders the interactive report and validates it against the report contract.** A report that fails the contract is recorded as an open issue of the run. An audit can also raise a suspected functional defect, which goes through the same verify step as any other bug.

Verdict words for the UX report are `PASS`, `PASS WITH ADVISORIES` and `BLOCKED`.

## 7. Outputs

Each run is one folder, and a run is never moved or renamed after it starts.

- **Consolidated run report** (Markdown and HTML): trigger, E2E stage, tests, bugs and UX suggestions in one place.
- **Run verdict:** `PERFECT`, `NEEDS_REVISION` or `HALTED`.
- **Test outcomes:** every test with its tags and final result.
- **Generated specs and feature notes:** what was tested and how.
- **Bug reports:** each bug written as a ticket, with evidence screenshots.
- **UX report:** interactive HTML, plus the findings and scorecard behind it.
- **Self-heal record:** the change log of every repair to the permanent suite.
- **Run log and summary:** timeline, phases, counts and cost.
- **Agent transcripts:** compressed, kept for debugging.

A sealed run keeps only this record. A halted or failed run keeps everything so it can be resumed (`--resume`) or debugged.

## 8. Optimisations and AI-SDLC alignment

- **Decomposition over monoliths.** One phase per session and only the needed skill loaded. This keeps context small and lets a small model do the work.
- **Right-sized retrieval.** Context depth follows ticket and PR complexity.
- **Explore once, reuse everywhere.** Trails feed authoring, bug reproduction and the UX audit.
- **Grounded authoring.** No spec step is written before the agent has done it in the app, which cuts hallucinated tests.
- **Self-healing at two levels.** The regression suite and the new specs can both repair themselves. This removes most of the upkeep that makes UI automation expensive.
- **Verification before filing.** A bug is filed only after an independent session reproduces it, which keeps false positives low.
- **Bounded growth.** The permanent suite grows by at most two journeys per run.
- **Controlled load on UAT.** Parallel browser workers are capped, and the run retries navigation on CloudFront rate-limit blocks.
- **Shift-left, continuous quality.** The regression gate runs on every UAT deployment, and feature QA starts from the ticket and PR themselves, so checks sit inside the delivery flow.
- **Traceability.** Every test, bug and UX finding links back to its ticket and PR.
- **Security.** Secrets stay in the environment, and the agent can read only the named ticket, its related items and the PR files ([security.md](security.md)).

## 9. Token and cost profile (Haiku 5.5)

Measured over eight recent completed ticket runs, all on Haiku 5.5 through Bedrock. Cost per run is exact, taken from the run summaries. Token figures are approximate: the agent transcripts of sealed runs are pruned, so the token mix comes from the sessions that were kept and is scaled to each run's recorded total cost.

**Cost per run**

| Measure | Value |
|---|---|
| Typical run (median) | about $1.3 |
| Average | about $1.4 |
| Range | $0.49 for a small change, up to about $3.15 for the largest run so far |
| Runs under $2 | 7 of 8 |
| Wall-clock time | about 50 minutes on average, from about 20 minutes (small ticket) to about 2 hours (heavy) |

A normal run lands in the $0.70 to $2 range.

**Tokens per typical run (approximate)**

| Token type | Amount |
|---|---|
| Fresh input | under 1K |
| Output | about 150K |
| Cache read | about 20M (14M to 45M depending on the feature) |
| Cache write | about 350K |
| Model steps | about 130 |

Cache reads are over 99% of all tokens, but they are billed at a small fraction of the normal input price. That is why a run that reads 20M tokens still costs about a dollar. The harness is built to keep the prompt prefix stable so the cache keeps hitting: small per-phase skills, a stable shared prompt, and sessions that do not reload unneeded context.

**Where the money goes**

| Phase | Share of cost |
|---|---|
| Explore and author | about 59% |
| UX audit | about 19% |
| Heal (feature and E2E) | about 13% |
| Plan, verify and promote | about 9% combined |

**What moves the cost**

- Feature size and complexity: more screens to explore and more specs to write.
- Heal attempts, capped at three per run.
- Whether the E2E stage found drift to repair.
- Length of the exploration: a long session builds a long cached history that is re-read on every step.

The sample is small (eight runs) and includes one unusually long run, so treat these as planning figures, not guarantees.

## 10. Current limits

- The harness **reads** Linear and GitHub but does **not** write to them yet.
- One run at a time. The agents share one set of permanent test files, and overlapping runs would make it hard to track edits to them.
- A single model serves every phase. That keeps cost low, but it is also a single point of quality.
- UAT sits behind CloudFront rate limiting, which limits how many browsers can run in parallel.

## 11. Roadmap

This is the direction of travel. Items are ordered by expected value and are proposals, not commitments.

**Next: close the loop**
- Post the run summary, verdict and bug reports back to the Linear ticket and the GitHub PR.
- Create Linear bug tickets from verified bugs, linked to the parent ticket.
- Make the harness a PR status check, so a `NEEDS_REVISION` verdict is visible before merge.

**Then: widen coverage**
- Add more core journeys to the regression suite, in the same positive, negative and edge pattern.
- Use run history to flag flaky cases and cases that heal repeatedly, as signals of unstable UI.
- Compare UX findings between runs, so regressions in the UX score are visible over time.

**Later: scale and tune**
- Allow safe parallel runs once permanent-suite edits are isolated per run.
- Route phases to different models by difficulty (for example a stronger model only for heal and verify), guided by per-phase cost and pass-rate data from run summaries.
- Trend dashboards over run history: pass rate, heal rate, bug yield, cost per run.
