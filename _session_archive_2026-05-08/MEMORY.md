# Memory — CityFurnish Ops Dashboard

Long-lived facts, conventions, and architecture. Update when something material changes.

---

## Stack

- **Frontend:** Single 30 MB HTML file. All data baked in as JS globals. No build step. Hosted on GitHub Pages.
- **Data ingest:** `refresh_from_metabase.py` pulls from Metabase API + Mongo (DT data via Metabase). Generates the dashboard HTML.
- **Auto-refresh:** GitHub Actions workflow `scheduled-refresh.yml` runs the Python script and pushes the regenerated HTML.
- **Refresh trigger:** "Refresh Now" button → Cloudflare Worker → GitHub `workflow_dispatch`.
- **Auth:** Password gate `cf@admin` (sessionStorage).
- **Repo:** `https://github.com/adityakumarCF/cityfurnish-ops-dashboard`
- **Live URL:** `https://adityakumarcf.github.io/cityfurnish-ops-dashboard/Task_Efficiency_Dashboard.html`

---

## Top-level dashboard tabs

| # | Tab | Page id | Notes |
|---|---|---|---|
| 1 | Overview | `page-overview` | Status snapshot |
| 2 | Task Efficiency | `page-task` | Has Task/Item view toggle |
| 3 | FAD Analysis | `page-fad` | Order-level First Attempt Delivery |
| 4 | FSD Analysis | `page-fsd` | Has Missing FSD amber pill |
| 5 | TAT Performance | `page-tat` | |
| 6 | Trip Efficiency | `page-trip` | |
| 7 | KPI Trend | `page-kpitrend` | Comparison/trend tab — see KPI Trend section below |
| 8 | Benchmark | `page-benchmark` | Single-screen filter view |
| 9 | Action Needed | `page-action` | Issue tracker |
| 10 | Simplified | `page-simplified` | Manager view (= Simplified) |

---

## Critical business definitions

| Concept | Predicate / Formula |
|---|---|
| **FAD%** | (FAD-true orders) ÷ (total orders). FAD-true = order is Done AND its OID is unique. |
| FAD OID uniqueness — Delivery / SR | Full-history OID count == 1 |
| FAD OID uniqueness — Pickup | OID count in rolling 2-month window == 1 (window: previous month start → max scheduled date) |
| **FSD%** | (FSD True) ÷ (FSD True + FSD False). FSD True = Done AND `sd <= ref` (ref = Requested Date else First Schedule Date). |
| **FSD False** | Done AND `sd > ref` |
| **FSD NoFS** | Pending (no first-schedule reference). Counts as FSD missed (Reschedule) by convention. |
| **Reschedule** | `FSD ∈ {'False', 'NoFS'}` — same predicate as **FSD Missed**. Used in TAT page, KPI Trend, FSD page, drill modals, Reschedule Reason Breakdown, Top Offenders. |
| **TAT (days)** | `Scheduled Date − ref` (ref = Requested else First Schedule). Negative TAT clamped to 0. |
| **TAT target** | Delivery 3, Pickup 7, SR 3 |
| **Within TAT** | Done AND has reference date AND `tat <= target` |
| **Vehicle-days** | Each (vehicle, day) tuple counted once. Used in Done Efficiency, capacity scoring, FAD/FSD vehicle tables. |
| **Done Efficiency** | Done tasks ÷ vehicle-days (per city) |

---

## Data model (Python-processed)

`PROCESSED_EXCEL_FULL.headers` — column index lookup via `PROC_IDX()`:
- City, Job Type, Category (Delivery/Pickup/SR), Done, VehicleType (Regular/Adhoc), Agent Name, Deliver Date, Scheduled Date, Transport, Adhoc Vehicle, VehicleConcat, Order Id, Ticket Number, first Schedule Date, FSD, Requested Date

`ITEM_EXCEL_FULL.rows` — barcode/item-level rows (13 cols): City, Job Type, Category, Physical Status, Vehicle Number, Agent Name, Scheduled Date, Ticket ID, SO Number, Product Name, Barcode, matchStatus, Movement.

`RAW_EXCEL` — raw Metabase data, original column order.

---

## Filters / state

| Global | Type | Purpose |
|---|---|---|
| `tvState[<report>]` | `'daily' \| 'weekly' \| 'monthly'` | Time view per report |
| `tvOffset[<report>]` | int | Window offset |
| `calDates[<report>]` | Date | Selected date per report (10 keys: task/fad/fsd/tat/trip/overview/kpitrend/benchmark/action/simplified) |
| `citySelection[<report>]` | `Set<City>` | City filter per report (init = `new Set(ALL_CITIES)`) |
| `taskViewMode` | `'task' \| 'item'` | Item-level toggle (Task Efficiency only) |

`ALL_CITIES` = `CITIES_ALLOWED.slice()` — kept fixed at 5 cities; never rebuilt from row data (regression risk).

`CITIES_ALLOWED` = `["Bangalore","Gurgaon","Hyderabad","Mumbai","Pune"]` (frozen).
`CITIES_ALLOWED_SET` = `new Set(CITIES_ALLOWED)`.

---

## KPI Trend tab — current architecture (post-2026-05-08)

### Layout (top-down)
1. **Time view bar** (Daily-only) + city filter
2. **City × Category Leaders** (orange bullet) — 4-matrix grid: FAD%, FSD%, Within TAT%, Tasks Done. Rows = 5 cities, columns = Delivery/Pickup/SR/Overall. 🏆 trophy on column leader, color-coded gap from leader. Uses `custCard` (kept).
3. **KPI Snapshot** (indigo bullet) — 2 stacked tables (FAD by job type, FSD by job type) using `compCard9`.
4. **Trip Efficiency** (purple bullet) — 3 stacked tables: Trip metrics + Single-trip % by city + Avg trips/order by job type. All `compCard9`.
5. **TAT Comparison** (teal bullet) — 3 stacked tables: Overall TAT metrics + Within TAT % by city + Within TAT % by job type. All `compCard9`.

### compCard9 component
Single source of truth for every comparison table. Signature:
```js
compCard9(title, mrows, firstColLabel)
```
- `firstColLabel` defaults to `'Metric'`; pass `'City'` or `'Job Type'` for breakdowns.
- Each `mrows` element built via `mRow(label, vA, vB, v7, v30, isPct, hb, dec, metricKey)`.
- Auto-generated 9 columns: `<First> | Day | Yesterday | 7d Avg | 30d Avg | Δ d-1 | Δ 7d | Δ 30d | Verdict`.
- **Insight strip auto-derived** from rows (biggest drop, biggest gain, declining/improving counts) — never hard-coded.

### Verdict logic
- All 3 deltas in improving direction → `▲ Improving` (green)
- All 3 declining → `▼ Declining` (red)
- Mixed → `↔ Mixed` (orange)
- All zero → `▬ Flat` (grey)
- For "lower-is-better" metrics, "improving" = delta < 0 (auto-flipped via `hb=false`)

### `hb` flag
- `true` → higher is better (FAD%, FSD%, Within TAT%, Single-trip %)
- `false` → lower is better (Reschedule, Multi-trip %, Waste, Adhoc %, Breach rate, Avg TAT, Reschedule rate, Avg trips/order)
- `null` → no judgement (raw counts: Tasks Done, Total trips, Unique orders, Total Assigned)

### Day-cell heat tint
- `kt-heat-good` (green) — Day better than both 7d & 30d averages
- `kt-heat-bad` (red) — Day worse than both
- `kt-heat-warn` (orange) — mixed

### Drill helpers
- `ktDrill(metricKey, dateSpec, label, evt)` — generic drill, uses kpitrend city selection
- `ktDrillCityCat(metricKey, cat, city, dateSpec, label, evt)` — for City × Category Leaders cells, hard-overrides city + category preds

---

## CSS classes added/used

| Class | Purpose |
|---|---|
| `.kt-verdict-pill`, `.kt-v-up/down/mixed/flat` | Verdict pill colors |
| `.kt-heat-good/bad/warn` | Day cell tints |
| `.kt-day-val` | Day cell font weight |
| `.kt-delta-up/down/flat` | Delta arrow colors |
| `.kt-insight-strip` | Insight strip container (orange tint) |
| `.kt-insight-chip`, `.gain`, `.loss` | Per-chip styling |

All dark-mode variants included.

---

## Common pitfalls / gotchas

1. **OneDrive sync lock** — file edits sometimes fail with `EUNKNOWN`. Wait 3s and retry.
2. **Thursday exclusion is universal** — every aggregation predicate includes `!isThursdayYMD(sd)`. Forget it and counts diverge.
3. **calDates[<report>] missing** — falls back to default. Always add new report keys to both JS init AND Python regeneration line in `refresh_from_metabase.py`.
4. **City allowlist** — must be applied at multiple layers: Python `ALLOWED_CITIES`, JS `recomputeAggregates`, ITEM_DATA loop, Benchmark, KPI Trend filters.
5. **Auto-refresh data commits** — they only touch data lines. Pull/rebase before pushing JS changes; no merge conflicts in practice.
6. **Password gate** — `sessionStorage.setItem('dashAuth','ok')` to bypass during testing.
7. **Tab slider positioning** — uses `offsetLeft/offsetWidth` (parent-relative), NOT `getBoundingClientRect` (breaks under overflow-clip).
8. **Var(--blue) is undefined** — use `--orange`, `--indigo`, `--purple`, `--teal`, `--green`, `--red` only.
9. **Vehicle counts in FAD/FSD vehicle tables** must use `vdReg/vdAdh/vdTot` (vehicle-days), not unique fleet `.size`. Otherwise weekly/monthly tables don't scale.

---

## Don't-touch list (per user direction)

- **City × Category Leaders section** — left intact in iteration 5.
- **`custCard` function** — still defined; only used by Leaders. Don't remove.
- Existing Excel exports / drill modal infra — don't refactor unless asked.

---

## Open / deferred items

| Item | Status |
|---|---|
| CBM capacity utilization | Plan written (`plans/plan-cbm-and-benchmarks.md`). Awaiting product/vehicle CBM master from founder. |
| Item-level KPIs beyond Task Efficiency | Plan written. Awaiting decision on toggle UX (Option 1/2/3). |
| Benchmark tab — Records / Performance Range | Lighter version shipped. Heavier version (4 sections, recommended thresholds, percentile thresholds) deferred. |
| KPI Trend streaks / percentile rank | Skipped (performance cost of 30 daily snapshots). |
