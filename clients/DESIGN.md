---
name: IIoT LoRa Network
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#1d4ed8'
  on-secondary: '#ffffff'
  secondary-container: '#4069f2'
  on-secondary-container: '#fffbff'
  tertiary: '#943700'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#dce1ff'
  secondary-fixed-dim: '#b7c4ff'
  on-secondary-fixed: '#001551'
  on-secondary-fixed-variant: '#0039b5'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  page-title:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  card-title:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  navigation:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  body-default:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-field:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 20px
  metadata:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  kpi-value:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-dense: 0.5rem
  margin: 1.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
  space-2xl: 2rem
---

# Design System: IIoT LoRa Network

**Version:** 2.0 — canonical, conflict-free specification  
**Application:** Industrial LoRa Event-Driven Fault Monitoring Web Dashboard  
**Design language:** Minimalist Industrial · Inter · Industrial Blue & Slate  
**Reference screens:** approved **Theo dõi (Light Mode)** and **Theo dõi (Dark Mode)** in the existing Stitch project.

> **Single source of truth:** The approved Theo dõi screens define the visual appearance of shared header, sidebar, iconography, input styling, table styling and spacing. New screens must look like the same application with only their page-specific main content changed. This document takes precedence over older generated DESIGN.md text and new page styling guesses. A screenshot is a visual reference, not permission to copy old or deprecated navigation submenus.

## 1. Visual theme and atmosphere

A calm, precise industrial monitoring application, not a marketing website and not a general-purpose analytics dashboard. Emphasize hierarchy, scannable device identifiers, unambiguous states, high-contrast text, consistent alignment and restrained use of accent colors. Use flat surfaces separated by subtle 1 px borders; no ornamental illustration, glow, gradients, glassmorphism or large decorative shadows.

**Application purpose:** The network uses LoRa to transmit *threshold-violation events*, not continuous normal telemetry. Hardware and backend detect faults, verify device activity/connection via heartbeat, calculate event values/durations, determine coverage relationships and supply all data. The frontend renders backend-provided information and provides navigation, filtering and export UI. It must not infer device state from an absence of events.

**Never generate:** fault acknowledgment/closure, incident assignment, resolved/open workflow, continuous traffic analytics, generic status dashboards, unnecessary KPI cards, or unsupported technical settings.

## 2. Color palette and functional roles

Use the following **approved tokens only**. The theme changes colors, not layout geometry or content.

| Semantic role | Light | Dark | Purpose |
|---|---|---|---|
| Page canvas | `#F5F7FA` | `#0B1220` | Full main application background |
| Card / table surface | `#FFFFFF` | `#172335` | Content containers |
| Header / sidebar | `#FFFFFF` | `#111C2E` | Persistent application chrome |
| Border / divider | `#E2E8F0` | `#334155` | Subtle 1 px structure |
| Primary text | `#0F172A` | `#F8FAFC` | Headings, values, regular text |
| Secondary text | `#475569` | `#CBD5E1` | Labels and metadata |
| Interactive text / icon | `#2563EB` | `#93C5FD` | Links, selected states and focus affordances |
| Selected sidebar background | `#DBEAFE` | `#1E3A5F` | Active route |
| Primary filled button background | `#2563EB` | `#2563EB` | Primary action, with white text |
| Active / operating | `#15803D` | `#4ADE80` | Backend-confirmed operating state |
| Connected | `#1D4ED8` | `#93C5FD` | Backend-confirmed connection state |
| Warning | `#A16207` | `#FBBF24` | Only confirmed warning severity |
| Critical | `#B91C1C` | `#F87171` | Only confirmed critical severity |
| Offline / unknown | `#64748B` | `#94A3B8` | Distinct text labels despite same neutral family |

**Color rules:** Ordinary sensor numbers, identifiers and timestamps use primary text, not arbitrary red/green. Use semantic color sparingly, with text or icon. Never infer that every temperature/speed event is critical. The same meaning must always use the same color family across pages. Meet WCAG 2.2 AA contrast when combining foreground and background colors; confirm every newly introduced combination.

**Prohibited competing palette:** Do not use the older violet-tinted background `#FAF8FF`, primary `#004AC6`, or any automatically generated Material color palette in place of the above tokens.

## 3. Typography

The only primary font is **Inter**, with Arial and sans-serif as fallbacks. Use Inter for Vietnamese and English, including Vietnamese diacritics. Keep one font and consistent metrics across both languages and themes.

| Element | Size | Weight | Line height |
|---|---:|---:|---:|
| Page title | 24 px | 600 | 32 px |
| Section/card title | 16 px | 600 | 24 px |
| Navigation / button | 14 px | 500 | 20 px |
| Table/body | 14 px | 400 | 20 px |
| Field label | 13 px | 500 | 20 px |
| Metadata | 12 px | 400 | 16 px |
| KPI primary number | 32 px | 600 | 40 px |

Use tabular numerals (`font-variant-numeric: tabular-nums`) for measurements, durations, timestamps and KPI counts. Prefer weights 400, 500, 600; no arbitrary 700+ weights. Do not add decorative underlines or arbitrarily uppercase all table headers. Do not shrink body/table text to fix overflow. Prevent unwanted text wrapping, clipping or overlap; retain full technical identifiers.

## 4. Components and styling

- **Icons:** Reuse the exact family, shapes, weights and mappings from the approved Theo dõi screens (Lucide-style outline). Standard size 20 px, compact actions 16 px. Do not invent a new logo, brand lockup or icon set.
- **Cards:** White / deep slate surface, subtle 1 px border, **8 px radius**, typically **16 px internal padding**; no decorative shadows.
- **Input/select/search:** Standard **40 px height**, subtle 1 px border, consistent 8 px corner radius. Use aligned labels and do not clip selection text. Focus must be visible.
- **Buttons:** Standard **40 px height**, 8 px radius; one clear primary action per page when required; secondary buttons outlined. No oversized controls.
- **Data tables:** Header approximately 44 px and standard body rows **48 px**. Content 14 px Inter. Subtle horizontal dividers, consistent numerical alignment, restrained hover/focus, no heavy vertical grid lines. Compact pagination stays within table boundaries. Do not hide required columns.
- **Status marks:** Small dot/icon + plain-language text; separately represent Connected and Active. Unknown and Offline need separate labels. Avoid large full-color background blocks.
- **Empty/loading/unavailable:** Show explicit empty text or loading skeleton. Use `—` for unavailable, never substitute `0` unless backend reports numeric zero.
- **Navigation affordance:** Clickable rows, cards and counts use hover, pointer and visible keyboard focus; never rely on underline-free color alone for accessibility.

## 5. Full-width layout principles

This is a real responsive desktop web app, **not a device mockup**. The application shell fills the browser viewport horizontally; the sidebar meets the **left viewport edge**; the top header spans the **full application width**; content extends to the right edge of the viewport **with internal padding**. Never center the whole app within an outer panel, phone/tablet bezel, padded artboard or rounded fake screen.

**Fixed reference geometry:**

| Token | Value |
|---|---:|
| Desktop design reference | 1440 × 900 CSS px |
| Secondary desktop validation | 1280 px viewport width |
| Header height | **56 px** |
| Sidebar expanded | **256 px** |
| Sidebar collapsed | **64 px** |
| Main horizontal padding | **24 px** on each side |
| Standard component gap | **16 px** |
| Dense gap (only when needed) | 8 px |
| Container radius | **8 px** |
| Normal table row | **48 px** |
| Normal control height | **40 px** |

**Width formula:** Usable main-content width = viewport width − current sidebar width − 2 × 24 px.

- At 1440 px with expanded sidebar: **1136 px** usable.
- At 1280 px with expanded sidebar: **976 px** usable.
- Page padding is **inside** the shell, not an outer viewport margin.
- All table/filter/card containers have fluid widths, `max-width: 100%`, `box-sizing: border-box` and no unbounded child min-width.
- Allow filter controls to wrap at narrower widths; tables may have scoped internal horizontal scrolling only when genuinely necessary. **Never** horizontally scroll or clip the whole desktop application.
- Preserve 24 px main padding where possible; respond to a narrow window without changing typography or hiding essential data.

## 6. Global shell and navigation — immutable

**Brand lockup:** `IIoT LoRa Network` with subtitle `Trạm giám sát`. Preserve positioning and styling from the approved references. Do not rename it to `LORA MONITORING` or invent another logo.

Exactly four top-level sidebar entries:

1. **Tổng quan** — direct navigation.
2. **Theo dõi** — direct navigation to the single event-monitoring table; **NO submenu**.
3. **Quản lý** — expandable; exactly `Gateway`, `Node`, `Người dùng`.
4. **Cài đặt** — settings page.

**Important:** `Tất cả lỗi`, `Nhiệt độ` and `Tốc độ` are **not sidebar items**. Temperature and speed are options in the `Loại lỗi` filter on Theo dõi. Only the current route, relevant expanded group and accessible focus/hover states may differ between pages.

Keep the header brand, status area, user area and sidebar icons/indentation exactly as on the approved Theo dõi reference screens. Do not add unrelated header toolbars, metrics, global configuration controls or redesign the chrome.

## 7. Approved page behaviors and boundaries

### Tổng quan

Minimal status summary only, without graphs: Gateway (connected and operating counts separately), Node (connected and operating counts separately), and recorded fault-event counts by type. Use **`Sự kiện lỗi`**, not `Lỗi đang mở`. Clicking a count navigates to a destination with the appropriate filter and retained area/time context.

### Theo dõi

One event table; default shows all fault types. Filters: area, fault type (`Tất cả`, `Nhiệt độ`, `Tốc độ`), time and Gateway/Node search. Required columns in order: `Thời gian`, `Khu vực`, `Gateway`, `Node`, `Loại lỗi`, `TB vượt ngưỡng`, `Thời lượng`. Event values and durations are returned by backend. Entire row navigates to the relevant Node detail page, **not to an incident modal**. No resolution status or processing actions.

### Quản lý → Gateway (List)

Page title `Gateway`; primary `Thêm Gateway` button, search and two **independent** status filters. One compact table: `Mã Gateway`, `Tên Gateway`, `Kết nối`, `Hoạt động`, `Khu vực`. Rows navigate to Gateway detail. Do not add unauthorized KPI strips, decorative info panels, new brand/header layout or maps. Gateway provisioning form is a separate subsequent design task.

### Gateway detail

Gateway identity; connected and operating status separately; read-only radio fields `Kênh`, `Tần số` (MHz), `Dải tần`; then a list of backend-provided covered areas with fault-event count for the selected time period. No frontend coverage calculations, radio-setting edits or signal propagation map. Area-row navigation opens Theo dõi with Gateway/area/time context.

### Node detail (future page)

Read-only Node identification and parameter choice; 3 KPIs: `Số sự kiện`, `Tổng thời gian vượt ngưỡng`, `TB vượt ngưỡng`. Time controls: `Tháng`, `Ngày`, `Giờ`, custom interval, plus visible `Xuất dữ liệu` UI button (export handled later by backend). Event-driven plot: at broad day/month scale render equally sized event dots at true timestamps; hover dot tooltip contains **only duration**, e.g. `90s`. User manually narrows interval; **do not auto-zoom on navigation**. At high resolution, draw separate line segments for actual recorded threshold-violation samples at real timestamps. Never connect different events, interpolate, replace gaps with zero or invent normal telemetry.

### Cài đặt (future page)

VI/EN language and Light/Dark/System theme settings are first-order choices. Additional settings require explicit product specification.

## 8. Screen creation and change policy

- **Design system = visual rules; page prompt = page-specific content and interactions.** Do not use this file as a request to generate every page.
- **Approved references win:** preserve approved Theo dõi header/sidebar exactly. If another screenshot conflicts, use the approved latest navigation and this contract.
- **Scope one functional page per request.** The page must eventually have two separate Light and Dark screens with identical geometry and content. To reduce drift, first design/approve Light; then generate Dark by theme-only transformation. Do not generate 4+ unrelated layouts in one request.
- **New screens may change only the page content and active navigation state.** Preserve global application shell and approved component language.
- Do not add features, cards, controls, labels or statistics that the page specification does not request.
- If a new request explicitly changes an approved system rule, update this document first and reconcile older screens; do not silently keep contradictory versions.

## 9. Acceptance checklist

- Brand, header, sidebar, icons and active navigation match approved Theo dõi references.
- Inter, token colors, 8 px corner radius, 40 px controls and 48 px table rows match the design contract.
- Both theme variants are identical except for semantic theme colors.
- No app-level overflow or clipped right-edge content at desktop widths 1280 and 1440 px; all required columns remain accessible.
- No unrequested chart, KPI, popup, incident status or configuration field.
- Data not provided by backend is marked unavailable; frontend does not infer health or radio coverage.
- Screen is legible in Vietnamese and English with meaningful hover/focus states.

---
# Supplementary Style Guidelines (Stitch Specification v2.0)

## Brand & Style

**Version:** 2.0 — canonical, conflict-free specification
**Application:** Industrial LoRa Event-Driven Fault Monitoring Web Dashboard
**Design language:** Minimalist Industrial · Inter · Industrial Blue & Slate
**Reference screens:** approved **Theo dõi (Light Mode)** and **Theo dõi (Dark Mode)** in the existing Stitch project.

> **Single source of truth:** The approved Theo dõi screens define the visual appearance of shared header, sidebar, iconography, input styling, table styling and spacing. New screens must look like the same application with only their page-specific main content changed. This document takes precedence over older generated DESIGN.md text and new page styling guesses. A screenshot is a visual reference, not permission to copy old or deprecated navigation submenus.

## Layout & Spacing

This is a real responsive desktop web app, **not a device mockup**. The application shell fills the browser viewport horizontally; the sidebar meets the **left viewport edge**; the top header spans the **full application width**; content extends to the right edge of the viewport **with internal padding**. Never center the whole app within an outer panel, phone/tablet bezel, padded artboard or rounded fake screen.

**Fixed reference geometry:**
- Desktop design reference: 1440 × 900 CSS px
- Header height: **56 px**
- Sidebar expanded: **256 px**
- Sidebar collapsed: **64 px**
- Main horizontal padding: **24 px** on each side
- Standard component gap: **16 px**
- Container radius: **8 px**
- Normal table row: **48 px**
- Normal control height: **40 px**

## Elevation & Depth

Spatial layering relies entirely on structured planar surfaces and high-contrast hairpins. This design system bans all ambient soft drop shadows, blurred overlays, and decorative dimensional lighting.

- **Zero-Shadow Baseline**: Standard analytical cards, charts, panels, tables, and side rails are flat (0px shadow) and define their boundaries strictly via a 1px solid border (`#E2E8F0` in light mode; `#334155` in dark mode).
- **Tonal Contrast Stacking**:
  - *Floor (Z0)*: Canvas background (`#F5F7FA` / `#0B1220`).
  - *Structural Containers (Z1)*: Modular cards, tables, control panels (`#FFFFFF` / `#172335`).
  - *Fixed Chrome (Z2)*: Lateral navigation rails and global telemetry headers bounded by 1px directional dividing rules.

## Components and styling

- **Icons:** Reuse the exact family, shapes, weights and mappings from the approved Theo dõi screens (Lucide-style outline). Standard size 20 px, compact actions 16 px. Do not invent a new logo, brand lockup or icon set.
- **Cards:** White / deep slate surface, subtle 1 px border, **8 px radius**, typically **16 px internal padding**; no decorative shadows.
- **Input/select/search:** Standard **40 px height**, subtle 1 px border, consistent 8 px corner radius. Use aligned labels and do not clip selection text. Focus must be visible.
- **Buttons:** Standard **40 px height**, 8 px radius; one clear primary action per page when required; secondary buttons outlined. No oversized controls.
- **Data tables:** Header approximately 44 px and standard body rows **48 px**. Content 14 px Inter. Subtle horizontal dividers, consistent numerical alignment, restrained hover/focus, no heavy vertical grid lines. Compact pagination stays within table boundaries. Do not hide required columns.
- **Status marks:** Small dot/icon + plain-language text; separately represent Connected and Active. Unknown and Offline need separate labels. Avoid large full-color background blocks.