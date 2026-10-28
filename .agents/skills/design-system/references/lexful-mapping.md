# Lexful to Fluent mapping

Use this with the stack check in `SKILL.md`. Everything marked **observed** was seen in Lexful's own screenshots or Storybook. Everything else is a proposal.

## 1. Stack decision and evidence

**Decision ([REDACTED], Oct 13):** shadcn/ui components (Radix + Tailwind) as the implementation, Microsoft Fluent UI as the design-alignment reference. Confirm with John when convenient (not blocking).

| Evidence (observed, Oct 2026) | Where seen | Points to |
|---|---|---|
| `data-slot="button"` on the Button element | Storybook, accessibility panel | shadcn/ui style components |
| Long utility class list (`inline-flex items-ce...`) | Storybook, accessibility panel | Tailwind CSS |
| Button controls `variant`, `size`, `asChild`, `disabled` | Storybook, Controls tab | shadcn with Radix (`asChild`) |
| Components `Command`, `Toaster`, `DateTimeRangePicker`, `BulkActionBar` | Storybook sidebar | cmdk, sonner, plus Lexful-built parts |
| "Microsoft Fluent UI Alignment: maintains design consistency with M365" | Lexful's internal Design System Consistency agent doc | The intended look and consistency goal |

Authority order: Lexful Storybook and style guide, then Fluent guidance, then shadcn defaults.

## 2. Lexful element to implementation and Fluent rationale

| Lexful element (observed) | shadcn implementation | Fluent rationale | Note |
|---|---|---|---|
| Right-side asset detail panel with tabs | Custom inline panel or `Sheet`, with `Tabs` | Drawer anatomy: title row with a quiet action area, tabs, body, footer | Header mixes title, "Set expiry", "Lex", "Download" and three icon buttons at similar weight |
| Ask Lex right-side panel | Custom panel or `Sheet` | Non-blocking drawer | Check Escape and focus return |
| Header search pill and search popup | `Command` (palette) with `Input Group` trigger | Fluent has no palette; follow SearchBox and focus rules | Keep Lexful's pattern |
| Filter chips (`@Organization`, `#Asset type`) | `Badge` / `Button` ghost | Tag guidance, visible labels | Keep behavior |
| "Filters", "All tags" buttons | `Button` outline, `Dropdown Menu` | Outline for secondary actions | |
| Floating "1 selected / Manage access / Manage tags / More actions" | Lexful `BulkActionBar` | Toolbar pattern | Intentional component; do not flag |
| "+ New" | `Button` default | One primary per surface | Matches the rule |
| Data tables | `Table` / `Data Table` | Table guidance | Sticky actions column is an opinion, not a defect |
| Left navigation | `Sidebar` | Nav, two levels max | |
| Empty states | `Empty` with `EmptyContent` button | Next step on every empty state | Documents has the shape and the button; Assets home lacks the button |
| Asset create form | `Field` around each control | Label, hint and error on every field | Errors appear one at a time today |
| Save confirmation | `Sonner` (transient) or `Alert` (persistent) | Toast and MessageBar guidance | Not observed in screenshots |
| Archive and delete confirmation | `AlertDialog` | Alert dialog, safe action focused | |
| Org picker (top-left) | `Select` / `Combobox` | | |
| Avatar (NJ) | `Avatar` | | |
| Expiry count badges | `Badge` | CounterBadge | |
| Hotkey hints (search shows a command-K hint) | `Kbd` | Not in Fluent | Good fit for technicians |

## 3. Known findings with a written remedy

| Finding | Source | shadcn implementation | Fluent rationale |
|---|---|---|---|
| Drawer header actions at equal weight (A11Y-04, BP-110) | Oct 1 screenshots | Title row; close and expand as `Button` ghost icon with `aria-label`; secondary actions in one `Dropdown Menu` "More"; at most one default Button | One primary action; quiet utility actions; group the rest |
| Validation errors one at a time (CRUD-01, BP-20) | Oct 1 observation | `Field` with an error message on every required control, shown together on submit | Inline errors, all at once |
| No confirmation after actions (CRUD-06, BP-108) | Oct 1 observation | `Sonner` toast for create, save, link; `Alert` for persistent notices | Transient vs persistent feedback |
| Assets home empty state has no CTA (CRUD-07, BP-106) | Oct 1 observation | `Empty` with a `Button` in `EmptyContent`, same as Documents | Every empty state offers a next step |
| Unrelated search results with no reason (SRCH-02, BP-11/12) | Oct 5 observation | Matched text in `font-semibold`; matched field as secondary `text-xs` text | Clarity of why something matched |
| No search guidance (BP-107) | Oct 1 screenshots | Placeholder naming what is searchable; recent items in `Command` | Guidance on first use |
| Save state unclear in editor (DOC-05) | Rulebook | `text-xs` status with `Spinner` while saving, then "Saved" | Visible system status |
| Icon-only buttons without names (A11Y-03) | Rulebook | `aria-label` or `Tooltip` | Accessible names |

## 4. What is already good (use for balance)

- Documents empty state has a clear inline CTA.
- Single primary "+ New" action per page.
- Search popup and Ask Lex drawer keep the page behind them (QA TC-SRCH103/112).
- Axe checks already pass on the Button component in Storybook (contrast 6.97 on the default Button).
