# Understand the feature, then derive the tests

Read this at the start of Explore, before you plan any case.

A test written only from what the UI showed asserts today's behavior, so it can never catch a bug. Tests that find bugs come from an **understanding of the feature that is independent of the page**. You build that understanding from the diff and from the code around it, write it down in `feature-map.md`, and only then walk the app and plan cases.

## Where the code is

`source-info.md` in the run directory names a read-only clone of the product repo (`runs/source/<repo>`) with the run's PRs fetched as branches `pr-<number>`. The working tree is the primary PR when it is open, otherwise `main`. If the file is missing, there is no clone: grep `context-pack.json` for the patch of one file at a time.

Browse with your normal tools: Read, Grep, Glob. Use git for history and for PR branches:

- `git -C <clone> diff origin/main...pr-N -- <path>` — what a PR changes in one file
- `git -C <clone> show pr-N:<path>` — a file as the PR leaves it
- `git -C <clone> grep -n "<symbol>" pr-N -- "<dir>"` — find uses on a branch
- `git -C <clone> log --oneline -n 15 -- <path>` and `git -C <clone> log -p -n 3 -- <path>` — why the code looks like this
- `git -C <clone> blame -L a,b <path>` — who last touched the lines in question

Never checkout, fetch, commit, or edit in the clone. Do not paste whole files into your answer; quote the lines you rely on.

## Build the feature map (budget: about a quarter of the session)

Work outward from the diff, in this order. Stop a branch of the search when it stops teaching you something.

1. **The change.** Read each changed file's diff. For every hunk write one line: what behavior is added, changed, or removed.
2. **The entry points.** Who calls the changed code? UI: which component renders it, which route or action opens it. API: the route, its schema, its hook chain (auth, validation). Grep for the symbol and read the callers.
3. **The path to the data.** Follow the call down: route → handler → service → repository → query, or component → hook → API client. Note each rule on the way: conditions, defaults, limits, permission checks, error codes, feature flags.
4. **The shared parts.** For every changed helper, component, schema, constant list, or CSS rule, grep for its other users. Each user is a surface that can break or fail to get the fix.
5. **The rules next door.** Read the file the change sits beside: the validator it relies on, the constants it imports, the CSS that overrides it, the stylesheet loaded after it. The commonest unrecorded bug is a rule in a file the PR did not touch.
6. **The authors' tests.** Read the tests in the PR and the neighbors of the changed file. They show what the authors thought of, and what they left out. An input class missing from them is where to look first.
7. **The history.** `git log -p` on the changed file. A recent fix next to the change often tells you the failure mode to retest.
8. **The words.** The ticket's acceptance criteria and the PR body. Each sentence is a claim.

Write `feature-map.md` in the run directory, short (about a page):

- **Purpose** — one or two sentences, in your words.
- **Behaviors** — a numbered list. Each item: the rule, and where it lives (`file:line` on the PR branch).
- **Surfaces** — every place the changed code is used (UI screens, API routes, shared components).
- **Inputs and boundaries** — values, limits, aliases, states, roles that change the outcome.
- **Risks** — where this change could be wrong or incomplete: rules in other files that conflict, surfaces the PR did not mention, old data or old values, roles.
- **Unknowns** — what the code does not settle and the live app must answer.

## Derive cases from the map

Every planned case cites a **behavior or risk number** from the map and states its oracle: the expected result and where it comes from (PR claim, AC line, `file:line`, or neighboring source). No oracle, no case. A case whose only source is "the UI showed it" is a gap, not a test.

For each behavior, cover what the rule implies:

- the main path, and the boundary on both sides (the value just in, just out, empty)
- each added option, alias, or id, and the nearest value that must be rejected or unchanged
- each new branch: the input that reaches it and the input that just misses it
- each surface in the map that uses the changed code, not only the one the PR mentions
- each role the rule is about
- old data and old values that must still load, display, and save

## Hunting bugs nobody recorded

After the claims pass, spend a short, fixed effort on the **Risks** list. Each risk is a hypothesis: write what you expect to see if the risk is real, then try to make it happen in the app or API.

- A fix on one side that does not reach the other (dropdown vs highlighter, editor vs read view vs print vs chat).
- A rule in an unchanged file that overrides the new one (a stylesheet, a default, a guard).
- A canonical value works but its alias, other case, or old spelling does not.
- Do the round trip: change it, reload, read it back by a different path (API after UI, UI after API).
- The console and failed network calls during the walk. An error while the visible result looks right is a finding.

Stop each hypothesis after the first reproducible mismatch, or after two clean tries. A mismatch you can reproduce is a finding: put it in `api-findings.json` with an `id` (F1, F2, ...), the oracle as `expected`, `actual`, and the evidence. Reproduce it a second time before you set `confidence` to `confirmed`. Write `steps` a person can follow in the browser or with plain curl, not Playwright calls.
