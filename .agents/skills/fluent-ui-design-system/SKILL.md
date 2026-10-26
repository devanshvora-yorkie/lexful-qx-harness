---
name: fluent-ui-design-system
description: "Use when auditing or proposing changes to Lexful's UI against the agreed design direction: shadcn/ui components (Radix + Tailwind) with Microsoft Fluent UI as the design-alignment reference. Covers action hierarchy, spacing, type, radius, behavior, accessibility, plus the Fluent to shadcn component map."
version: 0.2.0
status: "DRAFT, unsigned"
sources_verified: "2026-10-13 against storybooks.fluentui.dev (component index, Spacing, Border Radii, Typography, Button, Drawer) and ui.shadcn.com (component list, Sheet, Alert, Empty)"
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



# Fluent-aligned design for a shadcn/ui product (reference skill)

_Skill name kept as `fluent-ui-design-system` so existing links keep working._

**Purpose.** Give the audit agent one reliable place to look up (a) how Fluent UI solves a design problem, and (b) which shadcn/ui component Lexful would use to build it. Suggestions become specific ("use shadcn `Empty` with a button in `EmptyContent`, following Fluent's one-primary-action rule") and checkable, not vague ("make it cleaner").

**Companion files (read as needed):**
- `references/components.md` — every component in the official Fluent v9 index (the design reference).
- `references/shadcn-components.md` — the shadcn/ui components available today and how to compose them (the implementation).
- `references/lexful-mapping.md` — which Lexful screen elements map to which Fluent component, known gaps, and the evidence about Lexful's real stack.
- Used together with `lexful-ui-before-after` (builds the Before/After visuals) and `lexful-ux-audit-gate` (produces the findings).

---

## 1. Stay current: the official docs are the source of truth

This skill is a summary. Fluent changes, so when you can open URLs:
- Component index: `https://storybooks.fluentui.dev/react/llms.txt`
- Each component has a plain-text page linked from that index (pattern: `.../llms/components-<name>.txt`). Use the link exactly as written in the index.
- Design guidance: `https://fluent2.microsoft.design`
- shadcn/ui components: `https://ui.shadcn.com/docs/components` (each component has its own page; there are Radix and Base UI variants, and Lexful's `asChild` prop suggests the Radix one).

**Rule:** before you recommend a specific prop, variant or behavior, open that component's page and confirm it. If you cannot open it, write "from skill reference, not verified today" next to the claim. Never invent a prop name.

## 2. Stack decision: shadcn/ui components, Fluent-aligned design

**Decision ([REDACTED], Oct 13):** treat Lexful's UI as **shadcn/ui components (Radix + Tailwind)** with **Microsoft Fluent UI as the design-alignment reference**.
- **Implementation:** recommend shadcn components Lexful already has or can compose from them.
- **Design rules:** borrow Fluent's action hierarchy, spacing, type scale, behavior and accessibility guidance.
- **Never** recommend adopting the Fluent React library or a full redesign.

**Why this reading:** Lexful's Storybook shows `data-slot="button"`, Tailwind class lists, an `asChild` prop, and components named `Command` and `Toaster`, while Lexful's internal agent doc states "Microsoft Fluent UI Alignment". Together that means shadcn code with a Fluent-aligned look as the goal.

**Authority order when sources disagree:**
1. Lexful's Storybook and style guide (what is actually specified).
2. Fluent guidance (tie-breaker for new or unspecified cases).
3. shadcn defaults.

**Quick stack check each run (about 30 seconds):** confirm `data-slot`, `asChild` and Tailwind classes in the DOM, read the real `variant` and `size` options from Storybook's Controls tab, then write one line in the report: `Detected stack: <X>. Evidence: <what you saw>.` If it turns out to be Fluent React after all, only this section and the shadcn mapping change.

**Still to confirm with John (not blocking):** is the UI shadcn/Radix with Tailwind, and which Fluent aspects does Lexful intend to follow?

**Keep from Lexful:** brand colors, the product font, existing components such as `BulkActionBar`, `Command` and `DateTimeRangePicker`, and white-label behavior. Fluent's Segoe UI font and Microsoft blue are **not** part of the alignment.

## What "Fluent-aligned" means here (the adoption profile)

1. **Action hierarchy:** one primary action per surface; utility actions (close, expand) are quiet icon buttons with names; secondary actions are grouped in a menu.
2. **Spacing** on Fluent's 4px-based scale (maps directly to Tailwind, see 4b).
3. **Type** sizes from Fluent's ramp (caption 12, body 14, subtitle 20, title 24).
4. **Radius** consistent at 4 to 8px.
5. **Behavior and accessibility:** visible focus, Escape closes, focus returns to the trigger, targets at least 24px, icon buttons have names.
6. **Feedback:** transient message for success, persistent alert for page-level notices, inline field errors, empty states with a next step.
7. **Content:** sentence case, clear verbs.

## 3. Principles (paraphrased from Fluent 2)

Familiar and natural across platforms; built so people can focus on the task; consistent across products; clearly Microsoft in look. For Lexful the useful reading is: low visual noise, one clear primary action, predictable patterns, strong keyboard and focus behavior.

## 4. Verified tokens (official values)

Use token **names** in specs so engineers can map them. Exact colors, shadows, stroke widths and motion: fetch `theme-colors`, `theme-shadows`, `theme-stroke-widths`, `motion-tokens` pages from the index.

**Spacing** (`spacingVertical*` / `spacingHorizontal*`): None 0, XXS 2px, XS 4px, SNudge 6px, S 8px, MNudge 10px, M 12px, L 16px, XL 20px, XXL 24px, XXXL 32px.

**Border radius:** None 0, Small 2px, Medium 4px, Large 6px, XLarge 8px, 2XLarge 12px, 3XLarge 16px, 4XLarge 24px, 5XLarge 32px, 6XLarge 40px, Circular (fully round).

**Font family (base):** 'Segoe UI', 'Segoe UI Web (West European)', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif

**Type ramp (size / line height, weight):**
| Style | Size / line | Weight |
|---|---|---|
| caption2 | 10 / 14 | 400 (Strong 600) |
| caption1 | 12 / 16 | 400 (Strong 600, Stronger 700) |
| body1 | 14 / 20 | 400 (Strong 600, Stronger 700) |
| body2 | 16 / 22 | 400 |
| subtitle2 | 16 / 22 | 600 (Stronger 700) |
| subtitle1 | 20 / 28 | 600 |
| title3 | 24 / 32 | 600 |
| title2 | 28 / 36 | 600 |
| title1 | 32 / 40 | 600 |
| largeTitle | 40 / 52 | 600 |
| display | 68 / 92 | 600 |

**Token names seen in official examples** (use these exact names): `colorNeutralBackground1/3/4/5`, `colorNeutralForeground1`, `colorNeutralStroke1`, `colorBrandBackground2`, `colorStatusSuccessForeground1`, `colorPaletteRedForeground1`, `colorPaletteRedBorder2`, `strokeWidthThin`, `strokeWidthThicker`.

## 4b. Fluent scales as Tailwind classes (Lexful uses Tailwind)

Tailwind's default spacing is 4px per step, which lines up with Fluent. `[verify against Lexful's Tailwind config; they may have customized it]`

| Fluent token | px | Tailwind spacing class |
|---|---|---|
| XXS / XS / SNudge | 2 / 4 / 6 | `0.5` / `1` / `1.5` |
| S / MNudge / M | 8 / 10 / 12 | `2` / `2.5` / `3` |
| L / XL / XXL / XXXL | 16 / 20 / 24 / 32 | `4` / `5` / `6` / `8` |

| Fluent type style | Size / line | Tailwind (default scale) |
|---|---|---|
| caption1 | 12 / 16 | `text-xs` |
| body1 | 14 / 20 | `text-sm` |
| subtitle1 | 20 / 28 | `text-xl` |
| title3 | 24 / 32 | `text-2xl` |
| Strong weight (600) | n/a | `font-semibold` |

Radius: Fluent Medium 4px, Large 6px, XLarge 8px, 2XLarge 12px. In shadcn, radius comes from the `--radius` variable, and Tailwind radius class names differ between v3 and v4, so **specify px or the variable, and read Lexful's real `--radius` from the app**. Fluent's body2 and subtitle2 are 16/22, while Tailwind's `text-base` is 16/24, a 2px line-height difference.

## 5. Rules distilled from the official Button guidance (verified)

- Show **one primary** button that uses the theme color. If more than two actions have equal priority, make them all neutral.
- Place the primary on the left and the secondary just to its right. In dialogs and panels where people move through steps, right-align the group with the container. In single-page forms and focused tasks, left-align it.
- Appearances: `primary` (main action), `secondary` (default), `outline`, `subtle` (blends in until hover/focus, good for utility actions such as close), `transparent`. Sizes: small, medium (default), large. Shapes: rounded (default), circular, square.
- Do not use a button to navigate. Use a link. (Exception: Back/Next in a wizard.)
- Do not give default focus to a button that destroys data. Default focus goes to the safe action (Save or Cancel).
- Targets are at least 24 x 24 px.
- Sentence case. A clear verb, plus a noun if the verb is ambiguous ("Delete folder", "Create account").
- Icon-only buttons need an accessible name (`aria-label`) or a `Tooltip` with `relationship="label"`.

## 6. Drawer guidance (verified), relevant to Lexful's detail panel

- `InlineDrawer`: for content that does not need full attention; page stays usable. `OverlayDrawer`: only when full attention is required (uses Dialog under the hood; `modalType` can be `modal`, `non-modal` or `alert`; `alert` cannot be closed by Escape or outside click).
- Structure: `DrawerHeader` > `DrawerHeaderTitle` (title plus an `action` slot, typically a `subtle` close Button with `aria-label="Close"`), then `DrawerBody`, then optional `DrawerFooter` (primary action first, secondary after).
- Sizes: small 320px, medium 592px, large 940px, full 100vw. `DrawerHeaderNavigation` holds a toolbar (back, refresh, settings, close).
- Focus: use `useRestoreFocusTarget` and `useRestoreFocusSource` so focus returns to the trigger when the drawer closes.
- If drawer content has no focusable element, give `DrawerBody` `tabIndex={0}` so keyboard users can scroll it.
- Title renders an `h2` by default.

## 7. Quick-pick: job, Fluent pattern, shadcn implementation

shadcn names below come from the official shadcn component list (2026-10-13). Subcomponent names for Field are not verified here; open the shadcn page first.

| Job | Fluent pattern (design rationale) | shadcn implementation | Note |
|---|---|---|---|
| Record detail beside the list | `InlineDrawer` / `OverlayDrawer` | `Sheet` (`SheetHeader`, `SheetTitle`, `SheetFooter`, `side` prop) or a custom inline panel | Sheet is an overlay built on the Radix Dialog; if the list must stay usable, Lexful's panel is probably custom or uses `Resizable`. Check first. shadcn `Drawer` is the bottom-drawer pattern, not the side panel. |
| Confirm delete or archive | `Dialog modalType="alert"`, safe action focused | `AlertDialog` | Cancel is the default focus |
| Short "it worked" message | `Toast` | `Sonner` (Lexful has a `Toaster`) | Transient |
| Persistent page-level notice | `MessageBar` | `Alert` (`AlertTitle`, `AlertDescription`, `AlertAction`; `variant="destructive"`) | |
| Label, hint and error on a control | `Field` | `Field` (plus `Label`) | All required errors at once |
| Search box | `SearchBox` | `Input Group` or `Input` with icon | |
| Command palette | none in Fluent | `Command` | Keep Lexful's pattern |
| Choose from list / type to filter | `Combobox`, `Dropdown`, `Select` | `Combobox`, `Select`, `Native Select` | |
| Row or overflow actions | `Menu`, `MenuButton` | `Dropdown Menu` | |
| Primary + secondary action | `SplitButton` | `Button Group` + `Dropdown Menu` | |
| Actions for a selection | `Toolbar` | Lexful's `BulkActionBar` | Intentional component; do not flag |
| Tabs inside a panel | `TabList` | `Tabs` | |
| Data table | `Table`, `DataGrid` | `Table`, `Data Table` | |
| Tags, counts, status | `Tag`, `Badge`, `CounterBadge` | `Badge` | |
| Loading | `Skeleton`, `Spinner`, `ProgressBar` | `Skeleton`, `Spinner`, `Progress` | |
| Empty state | compose icon, text, primary button | `Empty` (`EmptyHeader`, `EmptyMedia`, `EmptyTitle`, `EmptyDescription`, `EmptyContent`) | Documents already follows this shape; Assets home lacks the button |
| Side navigation | `Nav` | `Sidebar` | |
| Hotkey hints | none in Fluent | `Kbd` | Useful for technicians |
| Help text | `Tooltip`, `InfoLabel` | `Tooltip`, `Hover Card` | |
| Dates | `DatePicker`, `Calendar` | `Date Picker`, `Calendar` | Lexful also has `DateTimeRangePicker` |
| Quiet icon button | Button `subtle` | Button `ghost`, icon size | Read Lexful's real variant names in Storybook Controls |

Closest button mapping (confirm against Lexful's variants): Fluent `primary` = shadcn `default`; `secondary` = `secondary`; `outline` = `outline`; `subtle` or `transparent` = `ghost` (or `link`); destructive actions use `destructive`.

## 8. Accessibility pointers

Official pages worth opening: Component labelling, Focus indicator, Notification Best Practices, Truncation, and the per-component pages for Button, Checkbox, Dropdown, Input, MenuButton, RadioGroup, SpinButton, SplitButton, Textarea (all under Concepts/Developer/Accessibility in the index). Utilities: `AriaLiveAnnouncer`, `useAnnounce`, focus-management hooks.

Lexful's bar is **WCAG 2.1 AA**. Fluent's guidance helps, but Lexful's own bar decides.

## 9. Output contract

Every recommendation must state:
1. **Implementation:** the shadcn component and subcomponents (and variant, props or Tailwind classes), verified in the shadcn docs or marked unverified.
2. **Design rationale:** the Fluent rule or component guidance followed, with the doc URL you opened (or "unverified").
3. **Scale equivalents:** spacing, radius and type, as Fluent token names and Tailwind classes.
4. Whether Lexful already does this (then say "no change needed").
5. The detected-stack line, and which source won if Lexful's Storybook and Fluent disagree.
6. Effort in S / M / L using the definitions in `lexful-ui-before-after`.

## Changelog
- **v0.2.0**: Direction set to shadcn/ui components with Fluent-aligned design. Added the authority order, the adoption profile, Tailwind equivalents of Fluent scales, a Fluent-to-shadcn quick-pick, and a new output contract. Replaced the "never assume Fluent" stack check with a quick stack check.
- **v0.1.0** — First version, built from the official Fluent UI React v9 index and docs (2026-10-13).
