# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MBTA Rail Alert Analysis Dashboard — a single-page data analytics app that visualizes 2025 service alerts for Boston-area rail transit (Subway, Light Rail, Commuter Rail). No backend server; fully static. Two files do all the work: a Python ETL script and a self-contained HTML dashboard.

## Deployment

- **Live site:** https://jonsims.github.io/mbta-rail-alerts-dashboard/
- **Local dev:** https://local.mbta-alerts (via Caddy)
- **GitHub Pages:** auto-deploys from `main` via `.github/workflows/pages.yml`

## Architecture & Data Flow

```
Alerts_2025/*.csv  →  preprocess_alerts.py  →  alerts_data.json  →  index.html (dashboard)
     (12 monthly CSVs,       (Python 3.11+,          (~440KB,           (~1900-line single-file
      50-70MB each)           stdlib only)           generated)          HTML/CSS/JS app)
```

### ETT.csv
A separate 50MB historical transit-time dataset (2022, half-hourly metrics). Not used by the dashboard — it's supplementary baseline data.

## Commands

```bash
# Regenerate the processed data (Python 3.11+ required, no pip deps — uses only csv, json, os, urllib, collections, datetime)
python3 preprocess_alerts.py

# View the dashboard (static file, no server needed)
open index.html
# Or via local Caddy: https://local.mbta-alerts
```

## preprocess_alerts.py (521 lines)

ETL script that reads monthly alert CSVs and outputs `alerts_data.json`.

### Pipeline steps:
1. **Read** all `Alerts_2025/YYYY-MM_ALERTS.csv` files
2. **Filter** to rail-only: route_type 0 (Light Rail), 1 (Subway), 2 (Commuter Rail)
3. **Deduplicate** by `alert_id` — keeps the row with the latest `last_modified_dt`
4. **Map codes to names** using two-tier lookup: tries `cause_detail`/`effect_detail` first (more specific), falls back to generic `cause`/`effect`
5. **Build records** with parsed datetimes, extracting month, day-of-week, hour, duration
6. **Aggregate** into monthly breakdowns, per-route stats, heatmap, duration stats — all deduplicated via `seen_*` sets to avoid double-counting
7. **Fetch route shapes** from MBTA V3 API (`api-v3.mbta.com/route_patterns`) — includes a Google Encoded Polyline decoder (`decode_polyline()`) to convert API responses to GeoJSON coordinates
8. **Write** `alerts_data.json`

### Key constants/mappings:
- `RAIL_ROUTE_TYPES` — `{"0", "1", "2"}` for filtering
- `ROUTE_TYPE_NAMES` — maps route_type codes to "Green Line", "Subway", "Commuter Rail"
- `ROUTE_COLORS` — official MBTA hex colors per route_id (Red: `#DA291C`, Orange: `#ED8B00`, Blue: `#003DA5`, Green: `#00843D`, Commuter Rail: `#80276C`, Mattapan: `#DA291C`)
- `ROUTE_DISPLAY_NAMES` — human-readable route names ("CR-Worcester" → "Worcester Line")
- `CAUSE_DETAIL_DISPLAY` / `CAUSE_DISPLAY` — two-tier cause mapping (21 named causes)
- `EFFECT_DETAIL_DISPLAY` / `EFFECT_DISPLAY` — two-tier effect mapping (12+ named effects)
- `DAYS_PER_MONTH_2025` — used for alerts-per-day calculations

### Deduplication strategy:
Uses multiple `seen_*` sets to count each alert only once per aggregation level:
- `seen_global`: `(alert_id, month)` — for global monthly aggregations
- `seen_per_rt`: `(alert_id, month, route_type_name)` — for per-route-type aggregations
- `seen_heatmap`: `(alert_id, start_date)` — for day-of-week × hour heatmap
- `seen_route`: `(alert_id, month, route_id)` — for per-route statistics

### Duration handling:
- Computed from `active_period_start_dt` to `active_period_end_dt`
- Capped at 720 hours (30 days) to remove outliers
- Stats: median (proper even-length average of two middle values), mean, 90th percentile

### Route grading:
- Based on severe alerts per day
- A: <0.2, B: <1.0, C: <3.0, D: <6.0, F: ≥6.0

## alerts_data.json Schema

Generated output consumed by the dashboard. Top-level keys:

```
{
  "generated": "2025-...",                  // ISO timestamp when JSON was generated
  "dataRange": { "from": "2025-01", "to": "2025-12" },  // month coverage
  "summary": { "totalAlerts", "totalAlertMonths", "topRoute", "topCause" },
  "months": ["2025-01", ...],              // 12 month labels
  "daysPerMonth": [31, 28, ...],           // for per-day rate calculations
  "causes": [...],                          // sorted by frequency descending
  "effects": [...],                         // sorted by frequency descending
  "causeTotals": { "Unknown": N, ... },    // global cause counts
  "effectTotals": { "Delay": N, ... },     // global effect counts
  "monthlyCause": { "Unknown": [N, N, ...], ... },     // cause → 12 monthly values
  "monthlySeverity": { "SEVERE": [...], "WARNING": [...], "INFO": [...] },
  "monthlyRouteType": { "Subway": [...], "Green Line": [...], ... },
  "monthlyEffect": { "Delay": [...], ... },
  "heatmap": [[...], ...],                 // 7 rows (Mon-Sun) × 24 cols (hours)
  "byRouteType": {                          // per route-type sub-aggregations
    "Subway": { causes, effects, causeTotals, effectTotals, monthlyCause,
                monthlySeverity, monthlyEffect, heatmap, duration },
    ...
  },
  "routeTable": [                           // per-route stats (22 routes)
    { "id", "type", "count", "avgSev", "topCause", "topEffect",
      "severe", "warning", "info", "months": {},
      "monthlySev": { "SEVERE": [...], "WARNING": [...], "INFO": [...] },  // per-route monthly severity
      "color", "displayName",
      "duration": { "median", "mean", "p90", "count" } },
    ...
  ],
  "routeTypeNames": ["Green Line", "Subway", "Commuter Rail"],
  "routeShapes": { "type": "FeatureCollection", "features": [...] },  // GeoJSON
  "duration": { "median", "mean", "p90", "count" }  // global duration stats
}
```

## index.html Architecture (~1913 lines)

Self-contained dashboard: HTML structure, CSS, JavaScript in one file.

### External dependencies (CDN):
- Chart.js 4.4.7 — all charts
- Leaflet 1.9.4 — interactive map with CartoDB basemap (light/dark variants)

### CSS design system:
- **Dark/light/system theme** via `[data-theme]` attribute on `<html>`
- Dark (`:root` default): `--bg: #0f1117`, `--surface: #1a1d27`, `--accent: #4f8cff`
- Light (`[data-theme="light"]`): `--bg: #f0f2f5`, `--surface: #ffffff`, `--accent: #2563eb`
- Theme-aware CSS vars: `--chart-grid`, `--chart-tick`, `--chart-label`, `--shadow`, `--heatmap-text`
- Responsive: `@media (max-width: 1100px)` and `@media (max-width: 600px)` breakpoints
- `.sr-only` class for screen-reader-only labels
- `.help-icon` / `.help-popup` for contextual help system

### JavaScript global state:
- `DATA` — loaded JSON object (set once from `fetch('alerts_data.json')`)
- `filters` — `{ routeType, route, cause, severity, monthFrom, monthTo }` (all strings, empty = no filter)
- `charts` — Chart.js instances: `{ trend, cause, effect, severity, routeType, modalTrend, modalSev }`
- `mapObj` — Leaflet map instance
- `mapLayers` — `{ routeId: L.geoJSON layer }` for route lines on map
- `sortCol`, `sortDir` — route table sort state
- `selectedRoute` — currently selected route ID (for table highlighting + map)
- `trendMode` — current trend chart mode: `'cause'|'severity'|'routeType'|'effect'`
- `routeSearchTerm` — route table search filter

### Initialization flow:
```
readUrlFilters() → fetch('alerts_data.json') → DATA = data → show dataMeta → populateFilters() → apply URL state to dropdowns → initMap() → renderAll()
```
Includes `.catch()` error handling with user-visible error state.

### URL state management:
- `readUrlFilters()` reads query params on load: `?rt=`, `?route=`, `?cause=`, `?sev=`, `?from=`, `?to=`
- `pushFilterState()` writes current filters to URL via `history.replaceState` (called in `renderAll()`)
- Enables shareable/bookmarkable dashboard states

### Core rendering pattern:
All filter changes trigger `renderAll()` which calls:
```
pushFilterState()             — sync URL with filter state
updateActiveFilters()         — filter tag pills in header
updateChartVisibility()       — hides redundant charts when filter active
renderDataQualityBanner()     — shows warning when >15% causes unknown
renderSummaryCards()          — 5 summary cards (uses monthlySev for accurate filtered counts)
renderDuration()              — median/mean/p90 duration stats + top-6 route durations
renderContextText()           — narrative paragraph summarizing the data
renderMapRoutes()             — redraws Leaflet route layers with grade-based styling
renderTrendChart()            — stacked bar (switchable mode, dynamic title showing % for cause mode)
renderCauseChart()            — horizontal bar (excludes Unknown/Other, shows known-cause %)
renderEffectChart()           — horizontal bar (promoted to first position — 100% classified)
renderSeverityChart()         — doughnut chart
renderRouteTypeChart()        — doughnut chart (always uses global data)
renderHeatmap()               — 7×24 grid with color intensity
renderRouteTable()            — sortable table with grade badges and severity bars
```

### Key features added (v2-v3):
- **Dark/light/system theme** — three-way toggle, persisted in localStorage, OS preference listener
- **Help tooltips** — (?) icons on every panel and summary card with contextual descriptions
- **Route-level filter** — `<select id="filterRoute">` lets users drill into a specific route
- **URL state** — all filter state persisted in query params for sharing/bookmarking
- **Export CSV** — downloads current filtered route table as CSV
- **About panel** — methodology, data source, known limitations
- **Grade disclosure** — hover tooltip on Grade column header shows threshold values
- **Data freshness** — header shows data range and generation date from JSON metadata
- **Accessibility** — `<label>` elements, `aria-label` attributes, `.sr-only` class
- **Mobile responsive** — 600px breakpoint, horizontal table scroll, stacked filters
- **Error handling** — `.catch()` on fetch with user-visible error message

### Chart layout:
- Effect chart now appears BEFORE cause chart (effects are 100% classified, causes ~6%)
- Cause chart subtitle dynamically shows actual known-cause percentage
- Trend chart title annotates "known causes only" when in cause mode

### Route modal:
Opens on table row click. Respects current month filters (no longer hardcoded to full year). Shows: alerts/day, severe/day, median duration, 90th percentile, total count, top cause, top effect. Contains monthly trend line and severity breakdown.

### Map rendering:
- Route lines styled by MBTA official colors
- Line thickness and opacity encode reliability grade (A=thin/faint, F=thick/opaque)
- Legend text: "Line thickness = reliability grade (severe alerts/day)"

## Data Quality Notes

- ~94% of alerts have cause "Unknown" — this is a source MBTA data quality issue, not a bug
- Effect data is 100% classified and more reliable for analysis
- The cause chart and trend chart (cause mode) exclude "Unknown" and "Other" to show the actionable 6%
- Dashboard shows a warning banner when >15% of causes are unknown
- Source CSVs in `Alerts_2025/` are large (50–70MB each, ~700MB total); the zip is 13MB
- MBTA V3 API is called only during preprocessing (for route GeoJSON shapes); dashboard is fully offline after that
- 33,929 unique alerts across 22 routes, 12 months of 2025

## Known Issues (from quality audit, 2026-02-26)

### Critical
- **Month-filtered rates are wrong in route table, context text, map, and CSV export.** `r.count` and `r.severe` are full-year totals but get divided by filtered-month `days`. Summary cards already fixed via `monthlySev`. Same pattern needs to be applied everywhere.

### High
- **ETL uses first-seen row attributes, not deduplicated winner.** The `alerts` dict tracks the latest `last_modified_dt` but `records` captures whatever version was seen first.
- **Display names inconsistent.** Route table, context text, modal, and summary cards show raw IDs (`CR-Worcester`) instead of display names (`Worcester Line`).
- **Light theme color contrast.** Grade badge colors A-D fail WCAG AA on white. `--orange`/`--green`/`--yellow` need darker light-mode variants.
- **No SEO meta tags.** No Open Graph, Twitter Card, description, or favicon for the public GitHub Pages site.

### Medium
- Keyboard: table rows, filter tags, help icons are mouse-only
- No modal focus trap
- Touch targets below 44px (theme toggle, about button, help icons)
- Heatmap unusable on mobile (~9px cells, no touch interaction)
- Tooltip division by zero with aggressive filtering (NaN%)

## File Inventory

| File | Size | Purpose |
|------|------|---------|
| `index.html` | ~87KB | Dashboard (HTML + CSS + JS) |
| `preprocess_alerts.py` | 21KB | ETL script |
| `alerts_data.json` | 440KB | Generated dashboard data |
| `.github/workflows/pages.yml` | 1KB | GitHub Pages deployment |
| `ETT.csv` | 50MB | Historical transit times (2022, unused by dashboard) |
| `Alerts_2025_metadata.md` | 3.7KB | FGDC-compliant data dictionary for CSV fields |
| `Alerts_2025/*.csv` | ~700MB | 12 monthly alert CSVs (source data) |
| `Alerts_2025.zip` | 13MB | Compressed archive of above |
