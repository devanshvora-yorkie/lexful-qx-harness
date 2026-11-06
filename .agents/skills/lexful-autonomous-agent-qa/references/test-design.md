# Tests that can catch a bug

A passing test is only worth something if it would fail when the product is wrong. These rules hold for every ticket, every journey and every phase. Read this before you plan cases and again before you hand off.

## The one question

For every test, answer: **what wrong behavior of the product makes this fail?** Write the answer in the **Fails when** column of the planned cases. If the honest answer is "almost nothing", or it fails only when the page does not load, strengthen the test or drop it. It proves presence, not behavior.

## Rules for the assertion

1. **Assert the behavior the title claims.** A title says "every", "only", "more than" or "keeps": the assertion checks exactly that. `> 0` does not prove "every", and `>=` does not prove "more than". Rename the test when it can only prove less.
2. **Use the exact oracle when one exists.** Prefer an exact expected value (a count, a name, a status) to a range or to "visible". Use a range only when the value truly varies, and say why.
3. **Take the expected value from an independent source.** Get it from something other than the code path under test: an API response, a total in the page header, the records you created, the oracle in `feature-map.md`. Never from another reading of the same screen state.
4. **Do not count what the page renders unless rendering is the behavior.** Lists virtualize and load lazily, so the DOM holds only some of the rows. Count from the API response or a total the page reports.
5. **Check the effect, not only the acknowledgement.** A 200, a toast or a `queued` status says the request was accepted. Read the result back: the record changed, the job's `total` is what you selected, the other records did not change.
6. **Test both sides of a limit.** The largest accepted value and the first refused one. One side alone does not locate the boundary.
7. **Empty proves nothing about behavior on data.** An action, a job or a filter that matched zero records can show that validation and status codes work. It cannot show that the action works, that a filter narrows, or that a risk does not exist.

## Exercising real behavior safely

"It would change shared data" is not a reason to skip behavior. It is a reason to choose one of these, in this order:

1. **Your own records.** Create records through the API or UI with a unique name or tag (`Date.now()` plus a random suffix), act on exactly those, verify the effect, and remove them in `afterEach`.
2. **Prove the scope before a bulk or filtered write.** Scope the selection to your unique name or tag, and first confirm that it matches exactly your records (the count the page or API reports equals what you created). Run the write only then. If you cannot narrow the scope to your own records, do not run it.
3. **Stop the request at the door.** For a write that cannot be scoped or undone (a grant, an invitation, a purge, a message to a person), drive the UI to the submit, capture the request with `page.route` or `page.waitForRequest`, assert its method, URL and body, then abort it. This proves what the client sends without changing anything.

Only when none of these can reach the behavior is it a gap, and the gap says which you tried and why they could not work. "Not walked", "not captured" or "would change data" alone is not a reason.

## Plan a useful set

- Cover what the rule implies, not only the main path: `positive`, `negative` and `edge`. A ticket's cases should not all be one type unless the change really has one kind of behavior.
- Choose the suite by what the case is for. `bvt` and `smoke` are the few that show the feature is alive. Boundaries, failure paths and role differences are usually `sanity` or `regression`.
- Anything a reviewer flagged, or that a follow-up ticket says is broken, is the first place to look. Try those hypotheses before you add more happy paths.
- When behavior depends on the role, run it as that role in the surface the user uses, not only in the API.

## Mapping to criteria and risks

- Map a test to an acceptance criterion only when the test **fails if that criterion is broken**. A test that merely passes through the same screen is not coverage: write a `gap` and say what is missing.
- A hypothesis is `refuted` only when you created the condition it needs and the product held. If the attempt could not create that condition (for example, it matched nothing), it is `unreached`, however cleanly the call returned.
- An observation that matches the defect the change claims to fix is never closed as `unreached` for one unknown fact: settle the fact with another persona, an API read or the deployed source, or file it as a suspected finding for verify (`phases/explore-author.md`, Hypotheses).
- **Deployed code is what you test.** `pr-brief.md` lists **Not on UAT**: commits of this ticket that the deployed build does not contain. A review fix there is not live: test the deployed behavior, and do not mark a criterion covered by code UAT does not run.

## Before you hand off

Go through `specs/` once. For each test, re-read the title, the **Fails when** cell and the assertions, and fix what does not line up. Check each `tests` mapping in `coverage.json` the same way. Two more minutes here costs far less than a heal round, and it decides whether the run means anything.
