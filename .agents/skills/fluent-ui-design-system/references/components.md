# Fluent UI React v9: component catalog

**Source:** official index at `https://storybooks.fluentui.dev/react/llms.txt`, fetched 2026-10-13. Descriptions are paraphrased from that index.
**Rule:** this list is complete for the index on that date, but props and variants change. Open the component's own page before recommending a prop. Mark anything you did not open as "unverified".
**Import:** components come from `@fluentui/react-components`; icons from `@fluentui/react-icons`.

## Foundations
| Item | What it is |
|---|---|
| `FluentProvider` | Turns a theme into CSS variables and passes settings to all components. |
| Theme: Colors, Spacing, Border Radii, Fonts, Typography, Shadows, Stroke Widths | The token pages. Theme Designer builds a custom brand ramp. |
| `Text` | Typography component, keeps text styles consistent. |
| `Label`, `InfoLabel` | A name for an input; InfoLabel adds an info button with correct accessibility. |
| `Divider` | Visual separator, horizontal or vertical, can hold content. |
| `Image` | Photo or illustration. |
| `Portal` | Renders content outside the DOM tree so it can escape overflow and z-index limits. |
| Motion (preview) | Fade, Scale, Slide, Collapse, Blur, Rotate, Stagger; motion tokens. |

## Buttons and actions
| Component | Use when |
|---|---|
| `Button` | Trigger an action. Appearances: primary, secondary (default), outline, subtle, transparent. Sizes: small, medium, large. |
| `CompoundButton` | A button with secondary text under the label. |
| `MenuButton` | A button with a chevron that opens a menu. |
| `SplitButton` | A primary action plus a secondary menu action. |
| `ToggleButton` | A button that can be on or off. |
| `Link` | Navigate between locations; standalone or inline. |
| `Toolbar` | Group buttons, menu buttons or checkboxes. |
| `Menu`, `MenuList` | A list of actions. (`MenuGrid` is preview.) |

## Inputs and forms
| Component | Use when |
|---|---|
| `Field` | Adds label, validation message and hint to any control. |
| `Input` | Single-line text. |
| `Textarea` | Multi-line text. |
| `SearchBox` | Search entry with clear behavior. |
| `Select` | Native `<select>` wrapper. |
| `Dropdown` | Button plus a list of options; typically in forms. |
| `Combobox` | Text field plus dropdown; choose or enter your own. |
| `TagPicker` | Combobox where each choice becomes a `Tag`. |
| `Checkbox`, `RadioGroup` | Multiple choice, single choice (use another control above about 5 options). |
| `Switch` | On/off with an immediate result. |
| `Slider`, `SpinButton` | Range value; bounded numeric input with +/- buttons. |
| `ColorPicker`, `SwatchPicker` | Pick a color, image or pattern. |
| `Rating`, `RatingDisplay` | Give a rating; show an average rating. |
| `DatePicker`, `TimePicker`, `Calendar` | Compat group: pick a date, a time, view a calendar. |

## Navigation and structure
| Component | Use when |
|---|---|
| `Nav` | Side navigation, up to two levels. |
| `TabList`, `Tab` | Single selection from tabs, content swaps. |
| `Breadcrumb` | Show the path to the current page. |
| `Accordion` | Expand and collapse sections. |
| `Tree` | Hierarchical, collapsible list. |
| `Carousel`, `CarouselNav` | Sliding window of items with pagination. |
| `Overflow` | Utility for overflow behavior in toolbars and tab lists. |

## Overlays and surfaces
| Component | Use when |
|---|---|
| `Dialog` | Window over the page; modal, non-modal or alert types. |
| `Drawer` (`OverlayDrawer`, `InlineDrawer`) | Side panel for details or settings; keeps context. |
| `Popover` | Content on top of other content. |
| `Tooltip` | Extra information about another component. |
| `TeachingPopover` | Guided tips and onboarding. |
| `Card` (`CardHeader`, `CardPreview`, `CardFooter`) | Container for one concept or object with actions. |

## Data display
| Component | Use when |
|---|---|
| `Table` | Low-level table for full customization. |
| `DataGrid` | Higher-level table with sorting, selection and more. |
| `List` | Vertically stacked items, focusable and selectable, with primary and secondary actions. |
| `Tag`, `TagGroup`, `InteractionTag` | Attributes, people or assets; InteractionTag has a primary and secondary action. |
| `Badge`, `CounterBadge`, `PresenceBadge` | Decoration, counts, availability status. |
| `Avatar`, `AvatarGroup`, `Persona` | Person or entity; group; avatar with presence and text. |

## Feedback and status
| Component | Use when |
|---|---|
| `Toast` | Temporary content on a separate, dismissible surface. |
| `MessageBar` | Important information about the whole application or surface. |
| `Spinner` | Short wait for content. |
| `ProgressBar` | Content being loaded or processed with known progress. |
| `Skeleton` | Placeholder while data loads, without blocking the rest of the UI. |

## Accessibility utilities
`AriaLiveAnnouncer`, `useAnnounce`, `useTypingAnnounce` (screen reader announcements); `useArrowNavigationGroup`, `useFocusableGroup`, `useFocusFinders`, `useModalAttributes`, `useRestoreFocusSource` and `useRestoreFocusTarget` (focus management, built on Tabster).

## Separate packages
Charts v9 (`storybooks.fluentui.dev/charts`), Fluent System Icons (`microsoft.github.io/fluentui-system-icons`), contributor packages.

## Not in the v9 index (do not claim these exist)
Empty state, command palette, bulk-action bar, date-range picker, rich-text editor, file uploader.
