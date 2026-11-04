# UX kit files (maintainer notes)

This file is for whoever updates the kit. No agent reads it; the kit files it describes live under `.agents/`.

These files come from the UX owner's kit (`lexful-ux-kit-v<N>.zip`; this is kit v12, audit skill v0.27.0). Map each kit file to the path below, then re-apply the harness changes listed at the end of this file:

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

`ux-auditor.md` is the prompt of the `ux-audit` phase, a session of the same `qa` agent and model as every other phase (there is no separate auditor agent). It keeps the kit text with these harness changes on top: the auditor writes only `ux-findings.json` and `ux-scorecard.json` (the server renders `ux-report.html` and runs the contract check), and Step 0 reads the ticket and its numbered criteria from `pr-brief.md` instead of editing `context-pack.json`, and the finding fields are listed with the exact names the generator reads (`reproSteps`, `evidence` as an array).

The server (`server/app/ux_report.py`) scores the findings, renders `ux-report.html` with the generator, then runs `scripts/check_report_contract.py`. Each failure is a `ux-contract` line in `run.log`, and a failing report is an open issue of the run. The verdict words are the contract's: `PASS`, `PASS WITH ADVISORIES`, `BLOCKED`.

The kit's own QA skill (`skills/lexful-autonomous-agent-qa/`), `qa-explorer.md` and `server/app/pipeline.py` are not used. The harness has its own QA skill and one `qa` agent.

The kit files are no longer copied as is. `skills/ux-audit/SKILL.md` was shortened for the harness: the Antigravity Docker section, the HTML layout and interaction sections (the generator and `report-contract.md` own those), and the instruction to consult `audit-preview-reference.html` are gone, and the verdict words are the contract's. `skills/design-system/SKILL.md` lost its Antigravity section and its Simple/Advanced output modes. When a new kit version arrives, re-apply these changes rather than overwriting. `audit-preview-reference.html` stays as a human-readable sample of the generator's output; the permission rules in `opencode.jsonc` keep the agent from reading it.
