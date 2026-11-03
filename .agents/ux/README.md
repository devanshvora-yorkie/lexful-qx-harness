# UX kit files

These files come from the UX owner's kit (`lexful-ux-kit-v<N>.zip`; this is kit v12, audit skill v0.27.0). Copy new versions in as they are and rewrite only the paths:

| Kit name | Here |
|---|---|
| `skills/lexful-ux-audit-gate/` | `.agents/skills/ux-audit/` |
| `skills/fluent-ui-design-system/` | `.agents/skills/design-system/` |
| `Lexful_UX_Rulebook_v0.5.md` | `.agents/ux/rulebook.md` |
| `Lexful_Bad_UX_Pattern_Library_v0.6.md` | `.agents/ux/pattern-library.md` |
| `lexful-ux-checks.yaml` | `.agents/ux/checks.yaml` |
| `QA_TRACEABILITY.md` | `.agents/ux/traceability.md` |
| `REPORT_OUTPUT_CONTRACT.md` | `.agents/ux/report-contract.md` |
| `templates/audit-preview-reference.html` | `.agents/ux/audit-preview-reference.html` |
| `prompts/qa-ux-auditor.md` | `.agents/prompts/ux-auditor.md` (merged by hand, see below) |
| `scripts/generate_ux_report.py` | `scripts/generate_ux_report.py` (one path added: it also looks for `.agents/ux/checks.yaml`) |
| `scripts/check_report_contract.py` | `scripts/check_report_contract.py` |

The same rewrites apply inside the files: kit file names become the paths above, and `runs/tickets/<ticket>/*/ux-findings.json` becomes "the run folders `history.md` lists", because a run started from a PR or a deploy can live outside `runs/tickets/`.

`ux-auditor.md` keeps the kit text with two harness changes on top: the auditor writes only `ux-findings.json` and `ux-scorecard.json` (the server renders `ux-report.html` and runs the contract check), and Step 0 reads the ticket and its numbered criteria from `pr-brief.md` instead of editing `context-pack.json`.

The server (`server/app/ux_report.py`) scores the findings, renders `ux-report.html` with the generator, then runs `scripts/check_report_contract.py`. Each failure is a `ux-contract` line in `run.log`, and a failing report is an open issue of the run. The verdict words are the contract's: `PASS`, `PASS WITH ADVISORIES`, `BLOCKED`.

The kit's own QA skill (`skills/lexful-autonomous-agent-qa/`), `qa-explorer.md` and `server/app/pipeline.py` are not used: they describe the older multi-agent setup.
