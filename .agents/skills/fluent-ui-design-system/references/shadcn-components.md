# shadcn/ui component reference

**Source:** official component list at `https://ui.shadcn.com/docs/components`, checked 2026-10-13. Compositions marked **verified** were read on the component's own page. For everything else, open the page before recommending props.
**Important:** shadcn components are copied into the app's own code, so Lexful may have changed them. The truth for Lexful is its Storybook (`packages/typescript/ui`). Lexful's Storybook already lists `BulkActionBar`, `Button`, `Command`, `DateTimeRangePicker` and `Toaster`.
**Variants:** shadcn publishes Radix and Base UI versions. Lexful's `asChild` prop points to the Radix version.

## Available components (official list)
Accordion, Alert, Alert Dialog, Aspect Ratio, Avatar, Badge, Breadcrumb, Button, Button Group, Calendar, Card, Carousel, Chart, Checkbox, Collapsible, Combobox, Command, Context Menu, Data Table, Date Picker, Dialog, Direction, Drawer, Dropdown Menu, Empty, Field, Hover Card, Input, Input Group, Input OTP, Item, Kbd, Label, Menubar, Native Select, Navigation Menu, Pagination, Popover, Progress, Radio Group, Resizable, Scroll Area, Select, Separator, Sheet, Sidebar, Skeleton, Slider, Sonner, Spinner, Switch, Table, Tabs, Textarea, Toast, Toggle, Toggle Group, Tooltip, Typography.
Newer additions on the site also include Attachment, Bubble, Marker, Message and Message Scroller (chat-style components).

## Compositions you will use most

**Sheet (side panel), verified.** Parts: `Sheet`, `SheetTrigger`, `SheetContent`, `SheetHeader`, `SheetTitle`, `SheetDescription`, `SheetFooter`, `SheetClose`. The `side` prop on `SheetContent` sets the edge. There is a "No Close Button" example. Built on the Radix Dialog (Radix docs cover focus and Escape behavior; verify there). It is an overlay by default.

**Alert (persistent notice), verified.** Parts: `Alert`, `AlertTitle`, `AlertDescription`, `AlertAction` (a button placed top-right). `variant="destructive"` for errors. Colors can be customized with classes.

**Empty (empty state), verified.** Parts: `Empty`, `EmptyHeader`, `EmptyMedia` (icon, image or avatar), `EmptyTitle`, `EmptyDescription`, `EmptyContent` (a button, input or link). Outline style through a `border` utility.

**Sonner / Toast (transient message).** Both appear in the list. Lexful has a `Toaster`, so check which one it wraps and where it is called. `[unverified details]`

**Field (label, hint, error).** In the list; open the page for its subcomponents and error pattern before use. `[unverified details]`

**Others commonly needed:** `Button` (read the variant and size options from Lexful's Storybook Controls), `Button Group`, `Dropdown Menu`, `Tabs`, `Table` and `Data Table`, `Badge`, `Tooltip`, `Kbd` (for hotkey hints), `Spinner`, `Skeleton`, `Progress`, `Separator`, `Resizable`, `Sidebar`, `Command`, `Combobox`.

## Rules of thumb
- Prefer composing components Lexful already has over adding new ones.
- Quiet icon buttons: Button `ghost` plus an icon size, always with an `aria-label` or a `Tooltip`.
- One default (primary) Button per surface; secondary actions in `outline` or `secondary`; grouped extras in a `Dropdown Menu`.
- shadcn `Drawer` is the bottom drawer; use `Sheet` for a side panel. `[verify on the Drawer page]`
