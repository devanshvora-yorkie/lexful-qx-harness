# UX Audit Report — Output Contract (v1.0)

Normative for every `ux-report.html` this kit produces. Where a skill, prompt or template
contradicts this file, this file wins. The reference implementation is
`scripts/generate_ux_report.py`; run it (`python3 scripts/generate_ux_report.py <run_dir>`)
instead of hand-writing markup, so the rules below are enforced by code.

`templates/audit-preview-reference.html` is **the output of that script** for a sample run
(LEX-3475). It is a generated artifact, not a hand-authored design: it exists so a reviewer can
see the finished shape, and it cannot drift from the generator. Regenerate it rather than
editing it. Its ticket, findings, scores and screenshots are illustrative only.

Origin: a LEX-3475 report shipped with an empty Acceptance Criteria Matrix, 6 boilerplate
checks copied from another journey, 14 raw `{'what': ...}` dicts, 14 "No expected vs actual
documented" placeholders, and two different verdicts on the same page. Every rule here exists
to stop one of those.

---

## 1. Read the ticket on every run

The report is about one ticket. Read it before writing any finding.

| What | Where it comes from |
|---|---|
| Problem statement | `context-pack.json` → `ticket.description`, first paragraph |
| Scope statements | the `Scope:` paragraph, split on sentence boundaries |
| Acceptance criteria | the `Acceptance:` bullets, or `ticket.acceptanceCriteria` as `- [ ] AC1: …` |
| Validation claim | the `Validation:` paragraph (tests, typecheck, lint, UAT smoke) |

- Copy acceptance criteria verbatim. Never paraphrase, merge, split or invent one.
- If the ticket has no acceptance criteria, say so in the matrix and in `ux-report.md`. An
  empty matrix with a reason is acceptable; an empty matrix with no reason is not.
- Label criteria `AC1…ACn` in ticket order. Label scope statements `Scope 1…Scope n`.
- The validation claim is **not** an audit result. Carry it as `OUTSTANDING` unless this run
  actually re-ran it.

## 2. Tag findings to the ticket

Every finding carries `acceptanceCriteria: ["AC2"]` — or `["Scope 2"]`, or `["Validation"]`.

- A finding that evidences nothing on the ticket still belongs in the report, but it does not
  close a matrix row. Say which row it does not close.
- The generator falls back to keyword matching when a finding is untagged, and prints
  "Linked by keyword match — tag the finding with this item's id" in the row. That is a
  visible defect in the finding, not a feature.
- Also tag `scope`: `"In scope"` when the finding belongs to the change under review
  (introduced or touched by this PR), `"Pre-existing"` when the behaviour predates it. A
  reviewer needs this to decide what blocks the merge.

## 3. One verdict, derived from severity

There is exactly one verdict per report. It appears in the nav badge, the hero card, the
integrity strip and the footer, and all four must read the same string.

| Condition | Verdict |
|---|---|
| Any S0 or S1 | `BLOCKED` |
| Any S2 or S3, no S0/S1 | `PASS WITH ADVISORIES` |
| Only O / nothing | `PASS` |

Never write a second verdict, and never let a run-directory name, a QA summary line or a
scorecard field contradict this derivation. If the scorecard disagrees with the severities,
the severities win and the report says so.

## 4. Acceptance Criteria & Scope Matrix

One row per acceptance criterion, per scope statement, and one for the validation claim.

Columns: `Item | Requirement / Scope | Evidence | UX Status`.

Statuses, in this order of precedence:

1. `BLOCKED` — an S0/S1 is attached.
2. `PARTIAL` — a scope statement with more than one clause where not every clause is backed
   by evidence. Name how many clauses are covered.
3. `VERIFIED WITH ADVISORY` — positive verification exists and an S2/S3 sits on the item.
4. `VERIFIED` — exercised, behaviour matches, no scored defect.
5. `DEFECT FOUND` — only a scored defect is attached, no positive verification.
6. `UNVERIFIED` — no finding evidences the item. Say so plainly; do not mark it done.
7. `OUTSTANDING` — the validation claim, carried over and not re-run.

Every row carries a one-line note explaining the status. Never leave a row with a status and
no reason.

## 5. Evaluated Checks Matrix

Scoped to **this ticket's journey**, not to the whole rulebook.

- Take the journey from `ux-scorecard.json` → `journey`, or infer it from the ticket, then
  select checks from `lexful-ux-checks.yaml` whose `journey` matches, plus every check whose
  `journey` is `All` (the A11Y set).
- A check is `DEFECT (Sx)` or `OBSERVATION` only when a finding cites it.
- Everything else is `N/A`, with the note "Not exercised in this run — no finding cites
  <ID>. Rule: <title>." A check this run never touched is never `PASS`.
- `PASS` appears only when the run records a real result for it (`checksEvaluated` in the
  scorecard).
- Print the tally under the table: `N exercised (x pass, y observation, z defect) · N not
  applicable`, and use the same numbers in the integrity strip.
- Never paste a result sentence describing a different journey. If the report mentions licence
  revocation, tenant downgrade, bulk assignment, filter counts or a Users/Clients tab on a
  create-drawer ticket, the matrix is boilerplate and must be rebuilt.

## 6. Finding cards

- **Expected and Observed are mandatory.** `expectedVsActual` reads `Expected: …` on one line
  and `Actual: …` on the next. For observations the second label is `Observed`. If a finding
  omits it, the generator falls back to the ticket's acceptance criterion — but the finding is
  still incomplete.
- The string "No expected vs actual documented." must never appear in a report.
- **Resolution is three labelled fields**, never a dict: `What to change`, `Developer`,
  `Design`. `solution` is an object with keys `what`, `developer`, `design`; a raw
  `{'what': …}` repr in the HTML is a bug.
- Show the scope chip (`In scope` / `Pre-existing`) on every defect card.
- Pattern chips show real pattern ids (`BP-73`). A taxonomy miss is omitted, not printed as
  "Unmapped / candidate".
- Evidence list first labelled `Evidence`, then the screenshot with the filename that matches
  the embedded image. If the evidence list names a second capture that is not embedded, say
  so in a note.

## 7. Hero, stats and integrity strip

- Hero carries the ticket **in full**: problem, scope, acceptance criteria, validation claim.
  Never truncate the ticket text.
- The hero summary line is one sentence about the audit (journey, criteria count, checks
  exercised, findings), not a copy of the ticket's problem statement.
- Four summary cards: Defects (S0–S3), UX Observations, Total Deductions, Design Stack.
- The integrity strip under the cards states three things: how many checks were exercised out
  of the matrix and why the rest are N/A; the verdict and its arithmetic (`deductions` from
  100 = `score`); and how many matrix items are still open.
- Defect counts in the stats card must add up to the number of defect cards rendered.

## 8. Never do these

1. Print a placeholder where a judgement belongs.
2. Print a raw dict, list repr or JSON blob as report copy.
3. Credit a check as `PASS` that this run did not exercise.
4. Show two verdicts, or a verdict that contradicts the severities.
5. Truncate the ticket, or drop its acceptance criteria from the matrix.
6. Report an in-scope defect as pre-existing, or the reverse, without saying which it is.
7. Claim the ticket's own validation (test counts, tsc, ESLint, UAT smoke) as audit evidence.
8. Leave the Acceptance Criteria Matrix empty without a stated reason.

## 9. Finding schema

```json
{
  "id": "UX-LEX3475-01",
  "checkId": "DOC-04",
  "lens": "b - Clarity and trust",
  "title": "Expiry day shifts one day earlier for users west of UTC after save",
  "severity": "S2",
  "deduction": 10,
  "confidence": "confirmed",
  "status": "Reported",
  "scope": "In scope",
  "acceptanceCriteria": ["AC2"],
  "journeyStep": "Create drawer → Set expiry → pick 20 Nov → Create",
  "expectedVsActual": "Expected: The picked day is shown in every viewer zone.\nActual: America/Los_Angeles reads 19 Nov, UTC reads 20 Nov.",
  "patternIds": ["BP-73"],
  "evidence": ["explore/ux/<capture>.png", "FEATURE.md: <fact>"],
  "screenshot": "explore/ux/<capture>.png",
  "screenshotCaption": "What the screenshot proves.",
  "solution": {
    "what": "Plain-English change.",
    "developer": "Implementation, with the acceptance check.",
    "design": "Design-system rationale."
  },
  "implementationShadcn": "Component and composition, or 'None needed'.",
  "fluentRationale": "Fluent pattern reference, or 'None needed'.",
  "qaRefs": [],
  "resolutionNote": "",
  "resolvedFromRun": ""
}
```

`ux-scorecard.json` supplies `score`, `totalDeduction`, `counts`, `journey`, `generatedAt`.
Its `verdict` field is advisory only; the report derives the verdict from severities.

## 10. Self-check before delivering

Run the gate before delivering. It reads the finished HTML and exits non-zero on any of the
rules above, so a regressed report fails instead of reaching a reviewer:

```bash
python3 scripts/check_report_contract.py <run_dir>          # or path to ux-report.html
python3 scripts/check_report_contract.py <run_dir> --json   # machine-readable
python3 scripts/check_report_contract.py <run_dir> --strict # warnings fail too
```

It checks, among other things: one verdict across nav/hero/integrity/footer and agreement with
the severity counts; stat-card counts against the cards actually rendered; matrix rows with a
status and a reason; the checks tally against the badges in the table; the integrity strip
against that tally; Expected/Observed and the three resolution fields on every card; duplicate
ids; and the presence of any placeholder, raw dict, boilerplate result sentence or truncated
ticket text.

The gate cannot tell whether a finding is *true* — only that the report is internally consistent
and contract-compliant. Truth still comes from the audit run.

Manual checklist:

- [ ] Matrix rows = acceptance criteria + scope statements + validation, none empty.
- [ ] Every defect card shows Expected and Observed, and three resolution fields.
- [ ] Checks table names this ticket's journey; the N/A count matches the tally line.
- [ ] One verdict string, everywhere.
- [ ] Ticket text complete in the hero; no truncation.
- [ ] No placeholder strings, no raw dicts, no boilerplate result sentences.
- [ ] Every finding tagged with an AC, Scope or Validation reference, and with `scope`.
