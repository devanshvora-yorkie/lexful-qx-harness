# What changed

## v0.28.0 (Kit v12) — Interactive Lightbox Zoom & Collapsible Ticket Block

- **Interactive Evidence Lightbox & Zoom Controls:**
  - Added dedicated zoom toolbar to the lightbox modal: **Zoom In (+)**, **Zoom Out (-)**, **Fit to Screen**, and **✕ Close** with real-time zoom percentage badge (`100%`, `125%`, `150%`, `175%`, `200%`, etc.).
  - Added click-to-zoom toggle on the lightbox image (1.75x enlarged mode with smooth pan and zoom cursor states).
  - Added keyboard shortcuts (`+`/`=` to zoom in, `-` to zoom out, `0` to fit, `Escape` to close) and mouse-wheel / trackpad zoom support.
  - Replaced fragile inline `onclick="openLightbox(...)"` string interpolation with element-based `openLightboxFromPreview(this)` utilizing `data-title` and `data-rel` attributes. Completely eliminates JavaScript `SyntaxError` crashes on finding titles containing single quotes/apostrophes and cuts report file size by ~48%.
- **Collapsible "Ticket as filed" Header:**
  - Converted the hero ticket description into an interactive `<details class="ticket-details">` disclosure component with animated chevron and `"Expand ticket text"` / `"Collapse ticket"` badge.
  - Removed duplicate `Acceptance` bullet list from the top hero block; acceptance criteria remain fully evaluated in Tab 3: Acceptance Criteria Matrix.
- **Contract Gate Validation:**
  - Full suite validated with `scripts/check_report_contract.py`: 29 rule groups passed, 0 failures, 0 warnings across all ticket reports.

---

## v0.27.0 — a gate, so a regressed report cannot ship

New: `scripts/check_report_contract.py`. It reads a finished `ux-report.html` and fails on the
things that actually went wrong on LEX-3475 and on anything structurally equivalent:

- more than one verdict, or a verdict that disagrees with the severity counts;
- the Defects stat card disagreeing with the defect cards actually rendered;
- an Acceptance Criteria & Scope row with no status or no stated reason, or an empty matrix;
- the checks tally line disagreeing with the badges in the table, or the integrity strip
  disagreeing with the tally;
- a card with no Expected/Observed callout, no What/Developer/Design block, or no Evidence list;
- duplicate finding ids;
- any placeholder string, raw dict literal, boilerplate result sentence from another journey,
  "Unmapped / candidate" pattern chip, or truncated ticket text;
- a report that is not self-contained (missing `<!DOCTYPE>`, no inline `<style>`, external script).

```bash
python3 scripts/check_report_contract.py <run_dir>            # exit 1 on any failure
python3 scripts/check_report_contract.py <run_dir> --json     # machine-readable
python3 scripts/check_report_contract.py <run_dir> --strict   # warnings fail too
```

Wired into `server/app/pipeline.py`: after the generator runs, the gate runs too, and a failure
is appended to the run's issues and the logbook rather than being silently shipped.

Proof it works: run against the original LEX-3475 report it reports 14 failures — including the
two conflicting verdicts, the empty matrix, the boilerplate "license revocation" line and all 14
cards missing Expected/Observed. Run against the current template and the regenerated sample it
reports 29 rule groups passed, 0 failures.

---

## v0.26.0 — the reference template is now a generated report

`templates/audit-preview-reference.html` (both kit trees: `.agents/ux/templates/` and
`ux-rulebook-and-patterns/templates/`) is replaced by the **output of
`scripts/generate_ux_report.py`** for the sample run LEX-3475, with a reference-template banner
at the top and a header comment naming the contract version it implements.

Why this matters: the old template was hand-maintained, so it could drift from the generator —
and it did, which is how a report ends up with the layout of one generation and the rules of
another. The template is now a build artifact. If the generator changes, regenerate the
template; never edit it by hand.

The sample content is illustrative: the ticket, findings, scores and the nine screenshots are
synthetic placeholders. Read it for structure, not for data.

Docs updated to match: the report sections of both `lexful-ux-audit-gate/SKILL.md` files, the
`ux-report.html` output line in both `qa-ux-auditor.md` prompts, the generator docstring, the
`.agents/ux/REPORT_OUTPUT_CONTRACT.md` preamble (both copies), and the audit instruction in
`server/app/pipeline.py`.

Regenerate the template with:

```bash
python3 scripts/generate_ux_report.py <sample_run_dir>
# then inject the banner, or keep a sample run dir and rebuild from it
```

---


Every UX audit run now builds its report from the ticket it is auditing, instead of from a
template with placeholders. The reference implementation is `scripts/generate_ux_report.py`.

## Files touched

| File | Change |
|---|---|
| `.agents/ux/REPORT_OUTPUT_CONTRACT.md` | **New.** Normative rules for `ux-report.html`. Where a skill, prompt or template disagrees, this wins. |
| `ux-rulebook-and-patterns/REPORT_OUTPUT_CONTRACT.md` | **New.** Same file, published copy. |
| `scripts/generate_ux_report.py` | Rewritten report logic (see below). Backup of the previous version: `scripts/generate_ux_report.py.bak`. |
| `.agents/prompts/qa-ux-auditor.md`, `prompts/qa-ux-auditor.md` | New Step 0 (read the ticket), extended finding schema, report rules pointing at the contract and the generator. |
| `.agents/skills/lexful-ux-audit-gate/SKILL.md`, `skills/lexful-ux-audit-gate/SKILL.md` | v0.25.0: report integrity rules, 4-card spec corrected, AC matrix and checks matrix redefined, changelog. |

## What the generator now does differently

1. **Reads the ticket every run.** Parses the problem statement, the `Scope:` sentences, the
   `Acceptance:` bullets (or `ticket.acceptanceCriteria`) and the `Validation:` paragraph out
   of `context-pack.json`. Labels them `AC1…ACn`, `Scope 1…Scope n`, `Validation`.
2. **Fills the Acceptance Criteria & Scope Matrix** — one row per item, each linked to the
   findings that evidence it, with a status: `VERIFIED`, `VERIFIED WITH ADVISORY`, `PARTIAL`,
   `DEFECT FOUND`, `UNVERIFIED`, `OUTSTANDING`, `BLOCKED`, plus a one-line reason. A multi-clause
   scope statement whose second clause was never exercised comes out `PARTIAL`, not `VERIFIED`.
3. **Scopes the Evaluated Checks Matrix to the journey.** Loads `lexful-ux-checks.yaml`, keeps
   the checks whose `journey` matches this ticket plus the `All` (A11Y) set, and marks every
   rule this run did not touch `N/A` with the reason. No more boilerplate `PASS` lines about
   licence revocations on a create-drawer ticket.
4. **One verdict**, derived from severity (`BLOCKED` / `PASS WITH ADVISORIES` / `PASS`) and used
   in the nav badge, hero, integrity strip and footer.
5. **No placeholders.** The "No expected vs actual documented." string is gone: the callouts use
   the finding's `expectedVsActual`, falling back to the ticket's acceptance criterion, and
   observations fall back to their own title. Raw `{'what': …}` dicts render as
   What to change / Developer / Design.
6. **Ticket block in the hero** — problem, scope, acceptance criteria, validation claim, in full,
   plus an integrity strip: checks exercised, verdict arithmetic, matrix items still open.
7. **Scope chips** on defect cards (`In scope` / `Pre-existing`), and "Unmapped / candidate"
   pattern chips are dropped instead of printed.

## How to check it

```bash
python3 scripts/generate_ux_report.py <run_dir>   # writes <run_dir>/ux-report.html
```

Then read the output against §10 of `REPORT_OUTPUT_CONTRACT.md`. The checks that would have
failed on the old LEX-3475 report: matrix rows present, no placeholder strings, one verdict,
checks table naming the ticket's journey, N/A count matching the tally line.

## Backwards compatibility

Old `ux-findings.json` files still render: missing `expectedVsActual` falls back to the ticket
criterion, a string `solution` still prints, and a missing `checksEvaluated` switches the
checks matrix to journey-scoped N/A. New findings should carry the fields in §9 of the contract.
