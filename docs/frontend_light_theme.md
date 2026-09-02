# CountyFlow V2-F2 Light Theme Specification

**Status:** IMPLEMENTED AND BROWSER VERIFIED — 2026-08-29

**Hard rule:** the application background, Sidebar, Topbar, dialogs, tables, Graph canvas, and in-app Monitoring surfaces are light. The main background is exactly `#FFFFFF`; cream, ivory, warm white, and half-dark migrations are rejected.

## 1. Design direction

CountyFlow is a calm, data-dense logistics decision system. Teal remains the brand accent but is reserved for selected navigation, primary actions, focus, key progress, and selected graph entities. Structure comes primarily from spacing, dividers, split panes, tables, rails, timelines, and inspectors—not nested cards or strong shadows.

## 2. Color tokens

```css
:root {
  color-scheme: light;

  --background: #ffffff;
  --surface-primary: #ffffff;
  --surface-secondary: #f6f8fa;
  --surface-subtle: #f2f5f7;

  --border: #d7dee5;
  --border-strong: #aab6c2;

  --text-primary: #17212b;
  --text-secondary: #4b5b6b;
  --text-tertiary: #687888;

  --brand: #0f766e;
  --brand-hover: #115e59;
  --brand-subtle: #e6f4f1;

  --success: #067647;
  --success-subtle: #ecfdf3;
  --warning: #9a6700;
  --warning-subtle: #fff7e6;
  --danger: #b42318;
  --danger-subtle: #fef3f2;
  --info: #175cd3;
  --info-subtle: #eff8ff;

  --focus-ring: #0d9488;
  --overlay: rgba(23, 33, 43, 0.40);
  --shadow-raised: 0 8px 24px rgba(23, 33, 43, 0.10);
}
```

No component may hard-code the current dark palette after migration. Semantic values use semantic tokens; brand teal is not a replacement for every blue, green, or status value.

### Contrast target

- Body, label, input, and table text: WCAG 2.2 AA, at least 4.5:1.
- Large display values: at least 3:1, with 4.5:1 preferred.
- Borders and focus indicators against adjacent colors: at least 3:1 where required for identifying a control.
- `--text-tertiary` is the lightest permitted normal text on white; placeholder text must be tested, not further faded.
- Primary button uses white text on `--brand`; Danger button uses white text on `--danger`.

## 3. Typography

Keep the current system-oriented family, removing reliance on an unavailable web font:

```css
font-family: Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei",
  "Noto Sans CJK SC", system-ui, sans-serif;
```

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| Page Title | 24px / 32px | 650 | Chinese primary page identity |
| Section Title | 16px / 24px | 650 | open section and panel heading |
| Card Value | 28px / 34px | 650 | truthful key metric only |
| Body | 14px / 22px | 400 | explanations and normal content |
| Label | 13px / 18px | 600 | form and compact section labels |
| Caption | 12px / 18px | 400 | provenance, timestamp, secondary metadata |
| Table | 13px / 20px | 400 | cells; headers use weight 600 |
| Button | 13px / 18px | 600 | all button variants |
| Input | 14px / 20px | 400 | controls and placeholder |

Chinese is primary for product titles. Technical names such as `Graph Memory`, `Runtime Thread`, and `Prometheus` are secondary labels. All-caps English eyebrow labels are reduced to provenance and true technical abbreviations only.

## 4. Spacing and sizing

Base spacing scale: `4, 8, 12, 16, 20, 24, 32, 40, 48`px.

- App content gutter: 24px at 1366, 28px at 1440, 32px at 1920.
- Section gap: 24px; related item gap: 12–16px.
- Table row: 44px compact, 52px comfortable; default operational density is 44px.
- Input/button height: 36px compact, 40px normal; primary page actions use 40px.
- Sidebar: 232px expanded, 72px collapsed.
- Topbar: 64px; no oversized hero header.
- Drawer: 420–520px depending on evidence density; Runtime Intervention may use 560px.

## 5. Radius, borders, and elevation

| Token | Value | Use |
|---|---:|---|
| `--radius-sm` | 4px | status, compact control |
| `--radius-md` | 6px | button, input, table container |
| `--radius-lg` | 10px | raised panel, drawer section |
| `--radius-pill` | 999px | status dot label only |

- Default panel border: 1px `--border`.
- Strong separation: 1px `--border-strong` only for active splitters, focused areas, and dangerous boundaries.
- Open sections prefer a top or bottom divider over a surrounding card.
- Shadow is limited to overlays, drawers, menus, and truly raised panels. Ordinary sections and tables do not receive shadows.

## 6. App Shell

- `body`, `.app-shell`, `.main-area`, and `.page-content` use `--background`.
- Main content uses a centered width capped near 1680px on 1920 displays; operational split panes may use the full available width.
- The shell owns responsive Sidebar behavior, Topbar identity, session state, and outlet state. Page components do not reimplement these regions.
- Overlay uses `--overlay`; dialogs and drawers always use `--surface-primary`.

## 7. Sidebar

- White background, right 1px `--border`, no dark residual strip.
- Logo retains the CountyFlow wordmark and a restrained teal mark.
- Default item: `--text-secondary`; hover: `--surface-subtle` with `--text-primary`.
- Selected item: `--brand-subtle`, `--brand` text/icon, optional 2–3px left indicator.
- Group labels use `--text-tertiary`, sentence case, and are hidden when collapsed.
- Collapsed items keep accessible names through tooltips and `aria-label`.
- 1366×768 may initialize collapsed; 1440 and above initialize expanded. User preference may persist locally, but cannot alter authorization.

## 8. Topbar

- White background with bottom 1px `--border`.
- Left: current workspace/page path and Chinese title.
- Right: bounded system state when relevant, notifications, display name, localized role.
- Development identity appears as a small `DEV AUTH` banner/control outside production builds.
- Large Admin badges, raw environment variables, provider secrets, and debugging strings are prohibited.

## 9. Buttons

### Primary

- Background `--brand`, white text, border `--brand`.
- Hover `--brand-hover`; focus uses a 2px `--focus-ring` outline with 2px white offset.
- Loading retains width, includes spinner plus action verb, and blocks duplicate submit.

### Secondary

- White background, `--border-strong` border, `--text-primary` text.
- Hover `--surface-secondary`.

### Ghost

- Transparent background, `--text-secondary`; hover `--surface-subtle`.
- Used for table actions, navigation-adjacent utilities, and low-emphasis controls.

### Danger

- Destructive final action: `--danger` background and white text.
- Danger Zone container uses `--danger-subtle` with a `--danger` left border and explicit risk copy.
- Runtime Override never uses the ordinary teal primary style for final confirmation.

Disabled controls retain readable text, have no hover elevation, expose a reason where business eligibility is involved, and are never the only indication of missing permission.

## 10. Forms

- Inputs/Textareas: white background, 1px `--border-strong`, `--text-primary`.
- Hover: border darkens; focus: 2px `--focus-ring` plus accessible outline.
- Error: `--danger` border and message; warning is not used for validation errors.
- Placeholder uses `--text-tertiary` and remains readable.
- Required, optional, help, and error copy are explicit. No label is represented by placeholder alone.
- Form submit defines default, hover, focus, loading, disabled, success, and error states.

## 11. Cards and container model

- MetricCard is white, 1px `--border`, and usually shadowless.
- At most one raised hierarchy is present within a workspace region.
- Prefer open metric strips, tables, dividers, split panes, rails, timelines, and inspectors.
- Card-inside-card layouts must be replaced with sections or dividers unless the inner element is an independent interactive object.

## 12. Tables

- Container: white with a subtle border or open section dividers.
- Header: `--surface-secondary`, `--text-secondary`, 600 weight.
- Row: white; horizontal `--border` divider.
- Hover: `#f2f8f7` or `--surface-subtle` depending on interactivity.
- Selected: `--brand-subtle` plus non-color selection marker.
- Focused row action: visible focus ring; row selection and action controls remain separate.
- Numeric values use tabular figures. Status columns use `StatusBadge` rather than raw colored text.
- Dense tables at 1366 may hide approved secondary columns or use an internal horizontal scroller; the entire page must not overflow.

## 13. Tabs

- Default pattern: underline tabs on white for page-level layer changes.
- Subtle segmented control is allowed for small bounded filters, using `--surface-secondary`; black segmented controls are prohibited.
- Selected tab uses `--brand` text and 2px underline.
- Full ARIA tab semantics, arrow-key navigation, visible focus, and associated tab panels are required.
- Memory labels are `向量记忆 / Vector Memory`, `图记忆 / Graph Memory`, and `共享记忆 / Shared Memory`.

## 14. StatusBadge

All statuses combine a small dot/icon with text. Suggested mapping:

| Status | Foreground | Background |
|---|---|---|
| 正常 / 完成 | `--success` | `--success-subtle` |
| 运行中 | `--brand` | `--brand-subtle` |
| 等待 / 未开放 | `--text-secondary` | `--surface-secondary` |
| 需复核 / 降级 | `--warning` | `--warning-subtle` |
| 异常 / 离线 / 过期 | `--danger` | `--danger-subtle` |
| informational | `--info` | `--info-subtle` |

Status text is localized in business surfaces; canonical technical values may appear in secondary detail.

## 15. Empty, loading, and error states

- EmptyState uses a plain icon, title, one-sentence explanation, and only a permitted action. It does not become a decorative illustration.
- Skeletons match the final metric/table/rail geometry and stop motion under `prefers-reduced-motion`.
- Business empty, API failure, 403, expired session, `NOT EXPOSED`, and unavailable system are separate components/copy variants.
- Error surfaces avoid raw stack traces, request headers, token content, vendor payloads, or secret-bearing URLs.

## 16. Graph Memory light design

- Canvas: `#ffffff` or `--surface-secondary`; no black gradient or neon glow.
- Grid, if needed: `#eef2f5` at minimal contrast; it must not compete with edges.
- Edges: neutral `#9aa8b6`; selected path may use `--brand` with increased width.
- Labels: `--text-secondary`; selected label `--text-primary`.
- Selected node: 2px `--brand` outline plus a non-color selection affordance.
- Node colors are limited, soft, and semantic by entity family:
  - Driver `#e8f1ff` / border `#5b8def`
  - Vehicle `#eef2f6` / border `#7a8998`
  - Route `#e6f4f1` / border `#0f766e`
  - Weather `#eef4ff` / border `#3b6fb6`
  - Anomaly `#fef3f2` / border `#b42318`
  - Resolution `#ecfdf3` / border `#067647`
- The Node Inspector is a white side panel with Type, Properties, Relations, Paths, and Evidence sections. Raw graph JSON is not the default view.
- Keyboard focus, node accessible names, selected state, and path descriptions are retained from the existing functional SVG approach; no large graph dependency is introduced.

## 17. Monitoring and charts

CountyFlow Monitoring is a white operations UI. Grafana remains an external specialist dashboard and is linked rather than visually cloned.

- Chart background: white; plot grid `#edf1f4`; axes/labels `--text-tertiary`.
- Primary line: `--brand`; secondary lines use only semantic success/warning/danger/info colors.
- Avoid rainbow palettes. Different series also use dash/marker/label distinctions.
- Tooltips are white with `--border`, `--text-primary`, and `--shadow-raised`.
- Stale and unavailable data are explicit states; last-known samples cannot masquerade as live.
- DataSource badges (`LIVE`, `VERIFIED`, `STALE`, `NOT EXPOSED`) are visible for Operator/Admin technical evidence, but not repeated across ordinary Dispatcher content.

## 18. Timeline, drawers, dialogs, and inspector

- Timeline rail: `--border`; event nodes use semantic outline and shape/icon differences.
- Drawer: white, left border, raised shadow, fixed header/action area, independently scrollable body.
- Dialog: white, max width appropriate to task, clear title/description, focus containment, and safe action order.
- Inspector: split pane with resizable or responsive width; technical details are progressive disclosure under “高级信息”.
- Runtime Intervention Danger Zone remains visually stronger than normal white panels through danger copy, border, icon, and final Danger button.

## 19. Responsive rules

| Viewport | Shell | Content behavior |
|---|---|---|
| 1366×768 | Sidebar collapsible and may default collapsed | 24px gutters, compact rows, essential columns first, no page-level overflow |
| 1440×900 | Sidebar expanded | balanced 12-column workspace, common target for browser QA |
| 1920×1080 | Sidebar expanded | centered max-width near 1680px; split panes and charts grow |

The current global `body { min-width: 1100px; }` must be reassessed during implementation. It may remain as a desktop-only floor only if 1366 behavior and internal panels remain non-overflowing; it cannot be used to conceal responsive failures.

## 20. Accessibility and motion

- Validate color contrast using automated axe checks and manual computed-color review.
- Focus cannot be removed; focus order follows visible order.
- Tables, dialogs, tabs, navigation, drawers, and row actions receive keyboard interaction tests.
- Status, graph node type, and chart series are not encoded by color alone.
- Motion duration is 150–200ms for hover, drawer, tabs, and status. No glow, floating, parallax, or large metric-count animation.
- `prefers-reduced-motion: reduce` disables non-essential transitions and skeleton shimmer.

## 21. Migration guardrails

1. Introduce tokens without changing page behavior.
2. Convert App Shell completely; do not ship a dark Sidebar with white content.
3. Convert common primitives and all their states.
4. Convert page surfaces one by one, including Graph and Monitoring.
5. Add role compositions after shared surfaces are reliable.
6. Scan source and computed styles for dark residuals; verify dialogs, drawers, selected/hover/focus, charts, Graph, and Monitoring.

No global search-and-replace of dark hex values is accepted as a migration strategy.

## 22. Implemented verification state

The canonical tokens now include background, primary/secondary/subtle/hover/selected surfaces, normal/strong borders, three text levels, brand states, semantic states, focus, overlay, and two shadow levels. The App Shell and existing feature surfaces were migrated component by component; the prohibited legacy dark palette is absent from `frontend/src`.

Playwright computed `rgb(255, 255, 255)` for the body, application shell, Sidebar, Topbar, Runtime Intervention dialog, Graph inspector, and Monitoring panel. Graph uses a permitted `rgb(246, 248, 250)` light canvas. The real screenshots cover all five roles, Memory, Graph, Monitoring, and the danger dialog at `docs/verification/frontend-role-ui/screenshots/`. Responsive checks at 1366×768, 1440×900, and 1920×1080 reported no document-level horizontal overflow.

Accessibility implementation includes visible `:focus-visible`, semantic table captions/headings, tab `aria-selected`, Graph node accessible names and `aria-pressed`, a keyboard-contained dialog with Escape and focus restoration, non-color status markers, and reduced-motion handling. No large UI, chart, or graph framework was added.
