---
name: lexful-ui-before-after
description: "Use after a Lexful UX audit to turn visual or layout findings into Before/After comparisons. Captures a Before screenshot of the real UAT screen, builds an After concept mock using shadcn/ui components with Fluent-aligned design, renders it at the same size, and writes the finding, the solution and the reasoning next to both images."
version: 0.3.0
status: "DRAFT, unsigned"
depends_on: [fluent-ui-design-system, lexful-ux-audit-gate]
config:
  before_after_comparison: false
  output_mode: simple
---
## Antigravity Docker Environment Testing
- When testing these skill files on the Antigravity platform, execution must run through the designated Docker container or image environment. 
- Ensure the Docker environment is running before validating the UX skill findings.

## Capability Toggles
- **Before-After Comparison**: The visual before-after generation capability can be toggled ON or OFF as required. By default, consider this OFF unless requested.

## Output Modes (Ticket Generation)
Provide output based on the requested mode to give the user full control:
- **Simple Mode**: Provide ONLY the detailed suggested solution. Hide all other contextual details, background, and internal reasoning.
- **Advanced Mode**: Display ALL details, including the detailed suggested solution, hidden background context, technical reasoning, and the full audit breakdown.



# Lexful UI Before/After

**Purpose.** Show Lexful's team, in one glance, what a finding looks like today (Before = real UAT screenshot) and what a better layout could look like (After = concept mock built from shadcn/ui components, following Fluent-aligned design rules), with the reason and the effort.

**Positioning (include in every report):** After images are **concept mocks for discussion, not the live product and not a commitment**. The audit finds and classifies issues; fixing is Lexful's call. These mocks show one possible fix, and are the starting point for the later development and design work.

**Read first:** `fluent-ui-design-system/SKILL.md` (stack decision, authority order, Tailwind equivalents, quick-pick), its `references/lexful-mapping.md` and `references/shadcn-components.md`, and `references/after-mock-template.html` in this skill.

**Direction (Oct 13):** implementation = shadcn/ui components (Radix + Tailwind); design rules = Fluent-aligned. Authority order: Lexful Storybook and style guide, then Fluent, then shadcn defaults. Never propose adopting the Fluent React library or a full redesign.

---

## Step 1: Inputs

1. The audit findings from `lexful-ux-audit-gate` (id, check id, severity, evidence). Checks in `lexful-ux-checks.yaml` marked `visual_fix: true` are the eligible ones; `shadcn_hint` names the shadcn implementation and `fluent_hint` gives the Fluent design rationale.
2. Logged-in access to UAT (the user logs in; never handle credentials).
3. The quick stack check from the Fluent skill (section 2), done now if it has not been done this run.

If there are no FAIL findings with `visual_fix: true`, say so, and produce only the "What is already good" section.

## Step 2: Choose what to show (keep it small)

- Candidates = findings with `visual_fix: true`, any severity (Observations are design suggestions about things that work, and are the natural home for Before/After pairs). Rank by severity (S0/S1 first), then by how often technicians hit that screen (search and save first).
- **Maximum 4 Before/After pairs per run**, plus 1 optional "already good" example for balance.
- Skip any finding where Lexful already follows the guidance. Write "No change needed" and why.
- One finding, one pair. Do not bundle unrelated changes in one mock.

## Step 3: Capture the Before

For each chosen finding:
1. Open the real screen in UAT in the state where the problem is visible.
2. Fixed capture settings, used for both Before and After: **viewport 1440 x 900**, same theme (note light or dark), 100% zoom. Crop to the relevant region (for example the drawer, the form, the popup), not the whole page, unless the finding is page-level.
3. Save as `demo-output/before-after/before-<finding-id>.png`.
4. Record: screen name, URL path, theme, role shown, date.
5. **Privacy:** UAT demo data only. Never capture password values, tokens or session data. If a screen shows credentials, skip it or mask them before saving.

## Step 4: Build the After mock

1. Start from `references/after-mock-template.html`. Copy it to `demo-output/before-after/after-<finding-id>.html`.
2. **Recreate the same region** with the same real text, labels and data you saw in the Before. Do not invent content, features or fields.
3. Apply only the change the finding calls for, using the **shadcn component** named in `shadcn_hint` (confirmed in the shadcn docs) and the **Fluent rule** in `fluent_hint` (confirmed in the Fluent docs). See the Fluent skill section 1 for both doc sites.
   - Follow the component's anatomy (for example `Empty`: `EmptyMedia`, `EmptyTitle`, `EmptyDescription`, `EmptyContent`).
   - Use Fluent's scales through the Tailwind equivalents (Fluent skill section 4b), and read Lexful's real `--radius` and colors from the Before.
   - **Keep Lexful's brand colors, font and information architecture.** Do not recolor to Microsoft blue and do not switch to Segoe UI.
   - Where Lexful's Storybook disagrees with Fluent, Lexful's Storybook wins.
4. Add a small caption in the mock corner: `Concept mock, not the live product`.
5. Render in the browser at the same 1440 x 900 viewport and the same crop, and save `demo-output/before-after/after-<finding-id>.png`.

## Step 5: Write the explanation (per finding)

Fill every field. Plain language, short.

- **Finding:** id, check id and rule ref (for example CRUD-06 / B3 / BP-108), severity, one-line problem.
- **Solution (in words):** what to change, 2 to 3 bullets.
- **What changed in the After:** numbered list (1, 2, 3) matching the visible differences.
- **Why it helps a technician:** one sentence tied to speed, clarity or safety.
- **Implementation (shadcn):** component and subcomponents, variant, props or Tailwind classes. Mark anything unverified.
- **Fluent rationale:** the Fluent rule or component guidance followed, token names, and the official doc URL you opened. Mark anything unverified.
- **Accessibility gain:** the concrete improvement (focus, name, contrast, announcement), if any.
- **Effort:** S (change a variant, prop, Tailwind class or copy), M (compose components Lexful already has, for example `Empty` + `Button` or `Alert` + `AlertAction`, no new data), L (a new component or pattern, new state, or backend support).
- **Risk and trade-offs:** at least one honest line (for example "Toasts can be missed by screen readers unless announced").
- **Confidence:** high, medium or low, and why.

## Step 6: Assemble the output

Save in the run folder:
1. `before-after/before-<id>.png`, `before-after/after-<id>.html` and `before-after/after-<id>.png` for each pair.
2. In `findings.json`, add a `beforeAfter` object to each finding that has a pair: `before`, `after`, `afterHtml` (paths relative to the run folder), `whatChanged` (array), `whyItHelps`, `accessibilityGain`, `effort` (`S`, `M` or `L`), `risk`. Also add a `nextSteps` list to the finding (strings, or objects with `owner`, `action`, `effort`).
3. Run `node playwright-starter/make-ticket-pdf.mjs <run folder>`. The PDF shows every pair side by side (Before on the left, After on the right) with the details and next steps, and adds a "Recommended next steps" page.
4. A standalone `before-after.html` is optional and only needed if the user asks for it.

## Step 7: Self-check before you finish

- [ ] Before and After use the same viewport, crop and theme.
- [ ] Same real text in both; the only differences are the intended ones.
- [ ] Every difference is listed in "What changed", and each one traces to a finding.
- [ ] shadcn and Fluent claims were checked against the official docs, or marked unverified.
- [ ] The detected-stack line is stated; effort wording matches it.
- [ ] Brand colors, font and information architecture kept.
- [ ] No credentials, tokens or customer data in any image.
- [ ] Every After says "Concept mock, not the live product".
- [ ] At least one risk or trade-off per suggestion.

## Don'ts

- Do not change anything in the live product. Mocks are local HTML only.
- Do not add features Lexful does not have.
- Do not propose a library migration (including Fluent React) or a full redesign.
- Do not suggest a change just because Fluent does it differently; tie it to a finding.
- Do not hide uncertainty. Low confidence is a valid answer.

## Changelog
- **v0.3.0**: Step 6 now feeds the PDF ticket pack through `findings.json` (`beforeAfter` and `nextSteps`) instead of separate HTML reports.
- **v0.2.0**: After mocks now use shadcn/ui components with Fluent-aligned design rules (was Fluent components). Output fields split into Implementation (shadcn) and Fluent rationale; effort scale redefined for existing shadcn components.
- **v0.1.0** — First version.
