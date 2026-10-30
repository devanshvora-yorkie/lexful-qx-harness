# UX kit files

These files come from the UX owner's kit (`lexful-ux-skills-and-rulebooks/`). Copy new versions in as they are and rewrite only the paths:

| Kit name | Here |
|---|---|
| `skills/lexful-ux-audit-gate/` | `.agents/skills/ux-audit/` |
| `skills/fluent-ui-design-system/` | `.agents/skills/design-system/` |
| `Lexful_UX_Rulebook_v0.5.md` | `.agents/ux/rulebook.md` |
| `Lexful_Bad_UX_Pattern_Library_v0.6.md` | `.agents/ux/pattern-library.md` |
| `lexful-ux-checks.yaml` | `.agents/ux/checks.yaml` |
| `QA_TRACEABILITY.md` | `.agents/ux/traceability.md` |
| `templates/audit-preview-reference.html` | `.agents/ux/audit-preview-reference.html` |
| `prompts/qa-ux-auditor.md` | `.agents/prompts/ux-auditor.md` |
| `scripts/generate_ux_report.py` | `scripts/generate_ux_report.py` (unchanged) |

The kit's own QA skill and `qa-explorer.md` are not used: they describe the older multi-agent setup. The server renders `ux-report.html` with `scripts/generate_ux_report.py`; the auditor writes only the JSON files.
