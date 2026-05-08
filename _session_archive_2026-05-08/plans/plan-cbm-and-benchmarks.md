# Plan: Item-Level + CBM Capacity Utilization Views

## Context

Founder wants two related views:
1. **Item-level** — see KPIs by barcode/item count instead of task count (already started; only Task Efficiency tab has it today)
2. **CBM capacity utilization** — see whether vehicles are being filled to capacity (e.g., a 10-CBM truck carrying only 7 CBM of items = 70% utilized)

**Why CBM matters:** Counting items is misleading. A 10-CBM vehicle carrying 8 items might be 90% full (small items) or 30% full (8 small items in a big truck). The truer efficiency metric is **CBM dispatched ÷ Vehicle CBM Capacity**.

**Status of inputs:** Founder will share product CBM master + vehicle CBM capacity later. **First we need to lock the VIEW DESIGN** — which tabs change in item/CBM view, which stay task-level, and what UX makes sense.

**What we already have:**
- `ITEM_EXCEL_FULL` rows: City, Job Type, Category, Physical Status, Vehicle Number, Agent Name, Scheduled Date, Ticket ID, SO Number, Product Name, Barcode, matchStatus, Movement (13 cols)
- Task/Item toggle on Task Efficiency tab only (`taskViewMode` global, `ITEM_DATA` structure)
- Vehicle tracking by `VehicleConcat` + `VehicleType` (Regular/Adhoc) — **no capacity field exists anywhere**

---

## View design — tab by tab decision

The core principle: split metrics into three families.

| Family | Examples | Item view applies? | CBM view applies? |
|---|---|---|---|
| **Count metrics** | Total Assigned, Total Done, Not Done | ✅ Yes — swap task count → item count | ✅ Yes — sum CBM instead |
| **Vehicle metrics** | Total Vehicles, Reg/Adhoc, Vehicle-days | ❌ Same — vehicle is vehicle | ➕ Adds capacity (CBM) overlay |
| **Timing metrics** | TAT, FAD, FSD, Reschedule | ❌ N/A — task/order-level by definition | ❌ N/A — capacity has no relation to timing |

### Per-tab recommendation

| Tab | Item view | CBM view | Notes |
|---|---|---|---|
| **Task Efficiency** | ✅ Already wired | ✅ Add CBM section in Item mode | Most natural home — counts → CBM is direct swap |
| **FAD Analysis** | ⚠️ Hide/grey toggle | ❌ N/A | FAD is order-level; "items in FAD orders" not really useful |
| **FSD** | ⚠️ Hide/grey toggle | ❌ N/A | FSD is task-level (sched date matched first) |
| **TAT** | ⚠️ Hide toggle | ❌ N/A | TAT is per-ticket time; items inside a ticket all have same TAT |
| **Trip Efficiency** | ✅ Add | ✅ Strongest fit — avg CBM/trip, low-utilization trip detection | This is where capacity insight is most actionable |
| **Overview** | ✅ Add | ✅ Add summary CBM utilization tile | Founder probably looks here first |
| **KPI Trend** | ✅ Add | ✅ Add CBM Utilization trend row | Trend over time → is utilization improving? |
| **Simplified** | ✅ Add | ✅ Add | Printable summary should reflect chosen view |
| **Action Needed** | ❌ N/A | ❌ N/A | Issue tracker, stays task-level |

### What this means for the toggle UX

Three concrete options, in increasing scope:

**Option A — Minimal (recommended for v1):**
Keep existing Task/Item toggle. When in Item mode, show extra CBM tile/section (no separate "CBM" state).
- Task Efficiency, Trip Efficiency, Overview, KPI Trend, Simplified all respect the same `taskViewMode` global
- FAD/FSD/TAT/Action ignore the toggle (their nature is task-level)
- Toggle button greys out / disables on tabs where it doesn't apply (so user understands)

**Option B — Three-state Task / Item / CBM:**
Same as A, but CBM is its own state. Item view shows item counts; CBM view shows CBM sums and utilization.
- More clicks, but cleaner separation between "see item-level numbers" vs "see capacity story"

**Option C — CBM as separate tab:**
A new top-level "Capacity" tab with all CBM analysis. Item view stays minimal.
- Most prominent placement; doesn't entangle with existing tabs

→ **Recommend Option A.** Smallest change, fastest to ship, founder can see CBM alongside item counts in the same view. If feedback says CBM needs its own surface, we promote to B or C later.

---

## KPI breakdown — what changes / stays / is new

### KPIs that CHANGE meaning when switching to Item view

| KPI | Task view | Item view | CBM view |
|---|---|---|---|
| Total Assigned | rows count | barcode count | sum(item CBM) |
| Total Done | done tasks | done items | sum(done item CBM) |
| Not Done | not-done tasks | not-done items | sum(pending item CBM) |
| Done % | done÷total tasks | done÷total items | done CBM ÷ total CBM |
| Done Efficiency | done tasks per vehicle-day | done items per vehicle-day | **done CBM ÷ vehicle CBM capacity = Utilization %** |

### KPIs that STAY THE SAME (vehicle-level, not item-level)

| KPI | Why |
|---|---|
| Total Vehicles | Vehicle is a vehicle regardless of what it carries |
| Regular Vehicles / Ad-hoc Vehicles | Vehicle attribute |
| Vehicle-days | Sum over days of unique vehicles |
| City vehicle threshold | Per-vehicle target, capacity-independent |

### NEW KPIs (CBM-only — only meaningful in CBM view)

| New KPI | Formula |
|---|---|
| **Capacity Utilization %** | sum(done item CBM) ÷ sum(vehicle-day CBM capacity) |
| Total CBM Dispatched | sum of CBM of all done items |
| Total CBM Capacity | sum over (vehicle, day) of that vehicle's CBM rating |
| CBM Slack | Total Capacity − Total Dispatched (wasted capacity) |
| Avg CBM/Vehicle | Total CBM Dispatched ÷ Total Vehicles |
| Per-vehicle utilization | per (vehicle × day): CBM filled ÷ CBM capacity |

### KPIs that don't apply at item / CBM level

- **TAT** (Turn Around Time) — task-level concept; one ticket has one TAT regardless of items inside
- **FAD** (First Attempt Delivery) — order-level (single trip per order)
- **Reschedule count** — task-level (the *task* was rescheduled, not individual items)
- **FSD** — task-level (date matched first scheduled date)

→ These metrics should only render in Task view. In Item/CBM view, hide or grey out.

---

## Data we need

### A. Product → CBM master
Founder will provide. Format options:
1. **CSV file** in repo root (`product_cbm_master.csv`) — import in `refresh_from_metabase.py`
2. **Hardcoded dict** in Python — only good for small fixed list
3. **Metabase table or sheet** — pull at refresh time

### B. Vehicle Type → CBM capacity
Two sub-options based on what data we have:
1. **Parse vehicle name** — vehicles like `VT-10FT-KA53AB2983` contain "10FT". Map sizes:
   - 10FT → ~8 CBM
   - 14FT → ~14 CBM
   - 17FT → ~22 CBM
   - 20FT → ~28 CBM
   - 32FT → ~50 CBM
   - Tata Ace / similar small → ~3 CBM
2. **Founder provides explicit vehicle → CBM list** alongside the product list

→ Recommend asking founder to provide the vehicle-type → CBM map explicitly so we don't guess.

---

## Design options for UI

### Option 1: Three-state toggle (Task / Item / CBM)
Replace existing 2-state pill with 3 buttons. Each click switches `taskViewMode`. Single linear flow.

**Pros:** Familiar, minimal UI change
**Cons:** CBM view re-purposes "vehicle efficiency" rows, which gets confusing

### Option 2: Two toggles (View: Task/Item) + (Show CBM: on/off)
Item view + checkbox to convert counts to CBM totals.

**Pros:** Clear separation, CBM is an overlay
**Cons:** Two controls to manage

### Option 3: Dedicated "Capacity Utilization" section (recommended)
Keep Task/Item toggle as-is. Add a brand-new section below the Vehicle Efficiency Summary called **"Vehicle Capacity Utilization (CBM)"** with:
- Per-city CBM utilization % bar
- Per-vehicle drill (vehicle-day CBM filled vs capacity)
- KPI strip: Total CBM Dispatched / Total Capacity / Utilization % / Slack CBM
- Visible only when `taskViewMode === 'item'`

**Pros:** Clean, additive, doesn't break existing toggle. CBM is a sub-feature of Item view.
**Cons:** None significant.

→ **Recommendation: Option 3.**

---

## Implementation phases

### Phase 1 — Data plumbing
1. Add `product_cbm_master.csv` (or similar) at repo root with `Product Name, CBM` columns
2. Add `vehicle_capacity_master.csv` with `Vehicle Type Pattern, CBM` (or hardcoded dict in Python)
3. In `refresh_from_metabase.py`:
   - Load CBM master at startup
   - Add `Item CBM` column to `ITEM_HEADERS` and to each item row (lookup via Product Name)
   - Add `Vehicle CBM` column to processed/item rows (lookup via Vehicle Type or pattern match)

### Phase 2 — Aggregation
In `recomputeAggregates`, alongside `ITEM_DATA` computation:
- For each item row in date range: accumulate `cbmDispatched[city]` (if Done) and `cbmTotal[city]`
- For each unique (vehicle, day) tuple: lookup `vehicleCBM`, accumulate `cbmCapacity[city]`
- Store on `ITEM_DATA.cbm = { byCity: {...}, total: {...} }`

### Phase 3 — UI
- Add new card "Vehicle Capacity Utilization (CBM)" below Vehicle Efficiency Summary, hidden unless `isItem`
- KPI strip (4 cards): Total CBM, Capacity, Utilization %, Slack
- Per-city table: City | CBM Dispatched | Capacity | Utilization % | Status (green ≥80%, orange ≥60%, red <60%)
- Drill: click any cell → modal showing item rows with CBM column + sum

### Phase 4 — Item view KPI updates
- When `isItem`, KPI labels stay item-count based (already done)
- Add a 6th KPI card to item view: "Capacity Utilization %"
- Existing "Done Efficiency" stays as items-per-vehicle (don't re-purpose)

---

## Critical files to modify

- `C:\Users\User\OneDrive - Default Directory\Documents\Ops_Reports\refresh_from_metabase.py`
  - Around line 570 (`ITEM_HEADERS`)
  - Around line 313 (`ITEM_PIPELINE`) — but no MongoDB CBM source, so add Python-side join after fetch
  - Add new helper to load product/vehicle CBM masters
- `C:\Users\User\OneDrive - Default Directory\Documents\Ops_Reports\Task_Efficiency_Dashboard.html`
  - `recomputeAggregates` (~line 5000) — add CBM accumulation block alongside ITEM_DATA computation
  - `renderTaskPage` (~line 4055) — add new section, conditional on `isItem`
  - Add ID anchor in HTML for the new section: `<div id="task-cbm-section" style="display:none"></div>`

---

## Verification

1. Run `refresh_from_metabase.py` locally with a small product CBM master → confirm `ITEM_EXCEL_FULL` rows have `Item CBM` field populated
2. Open dashboard → Task Efficiency tab → click "Item" toggle → new "Vehicle Capacity Utilization" card appears below Vehicle Efficiency Summary
3. Numbers reconcile:
   - Sum of per-city CBM Dispatched = Total CBM Dispatched KPI
   - Utilization % = Total CBM Dispatched ÷ Total Capacity (within ±0.1%)
4. Drill from any CBM cell → modal lists rows whose CBM sum equals the cell value
5. Switch back to "Task" toggle → CBM section hidden, classic view restored

---

## Open questions for user

1. **Product master format** — CSV in repo, Metabase table, or hardcoded list?
2. **Vehicle capacity source** — does founder have a vehicle-type → CBM mapping, or should we parse from vehicle names (10FT/14FT/etc.)?
3. **Default CBM** when a product isn't in the master — count as 0, exclude, or assume average?
4. **Toggle UX** — go with Option 3 (dedicated CBM section in Item view) or Option 1 (Task/Item/CBM three-state)?
5. **Scope** — CBM section only on Task Efficiency tab, or also Overview / KPI Trend?

---

# Plan 2: Missing FSD Highlighter + Performance Benchmarks Tab

## A. Missing FSD Highlighter (small feature)

**Problem:** Some Done orders have neither Requested Date nor First Schedule Date. They get flagged `MISSING` in the data but currently sit silent — no visual call-out. Operations needs to spot these to fix them in the source.

**Where:** FSD tab top bar, next to the EXCLUSIONS pill.

**UX:** Amber pill labeled `⚠ MISSING (N)` showing live count of MISSING rows in current date+city scope. Click → drill modal with columns: City, Job Type, Category, Order ID, Ticket #, Scheduled Date, Requested Date (blank), First Schedule Date (blank), Agent. CSV download supported.

**Visibility rule:** Only shows when count > 0. Hidden otherwise.

**Implementation notes:**
- Predicate: `r[FSD] === 'MISSING'`
- Reuse existing drill modal infra (`openDrillBase`)
- Add anchor `<div id="fsd-missing-pill"></div>` in FSD time-view-bar
- Render in `renderFsdPage` using same data scope as the rest of the FSD page

**Files:**
- `Task_Efficiency_Dashboard.html` — `renderFsdPage` (add count + click handler) + HTML anchor in the FSD section near `excl-btn-wrap-fsd`

**Sample mockup:** `missing-fsd-samples.html` (3 placement options drawn out, recommend pill + modal combo)

---

## B. Performance Benchmarks / Thresholds Tab

**Problem:** Currently we eyeball "good" vs "bad" performance. Founder wants the dashboard to compute **historical best & worst per city, category, and report** — so thresholds become data-driven, not guesses.

**Tab name:** "Benchmarks" (alt: "Performance Range" / "Records" / "Thresholds")

**Tab placement:** New top-level tab `8. Benchmarks` after `7. Action Needed`. Fits the existing seg-tray.

### What it analyzes (using full 4-month historical data in `PROCESSED_EXCEL_FULL`)

For each metric, find best & worst over the dataset, sliced by:
1. **City** (Bangalore / Gurgaon / Hyderabad / Mumbai / Pune / Chennai)
2. **Category** (Delivery / Pickup / SR)
3. **Report** (Task / FAD / FSD / TAT / Trip)

Metrics analyzed:
- Done % (Task Efficiency)
- FAD % (single-trip orders)
- FSD True %
- Within TAT %
- Avg TAT (days) — lower is better
- Reschedule rate %
- Single-trip %
- Done Efficiency (per vehicle-day)

### Section layout (one tab, four sections)

**Section 1 — Headline records**
KPI strip showing all-time bests for each metric across all cities/categories. E.g. "Best Done %: 96.5% (Pune, 12 Apr 2026)".

**Section 2 — City benchmarks table**
Rows = cities, columns = each metric's best/worst/median. Columns:
| City | Done % Best | Done % Worst | FAD % Best | FAD % Worst | FSD % Best | FSD % Worst | TAT% Best | TAT% Worst | Reschedule Best | Reschedule Worst |

Cells link to drill: click "Best" → opens day's snapshot, "Worst" → same.

**Section 3 — Category benchmarks**
Same shape but rows = Delivery / Pickup / SR.

**Section 4 — Recommended thresholds (auto-derived)**
A computed table:
| Metric | Suggested Green Threshold (75th percentile) | Suggested Red Threshold (25th percentile) |
| Done % | 90% | 75% |
| FAD % | 85% | 70% |
| ... |

Founder can use these to set actual targets in the system (replaces today's hardcoded thresholds in `CA_THRESHOLDS`).

### How to compute (algorithm)

1. Walk `PROCESSED_EXCEL_FULL.rows`
2. Group by `(date, city)` and `(date, category)` — produce daily slices
3. For each slice, compute every metric (Done %, FAD %, FSD %, etc.)
4. Aggregate: min, max, median, p25, p75 across all slices for each (city) / (category) combo
5. Cache in a global `BENCHMARKS = { city: {...}, category: {...}, report: {...} }`

This runs once at page load (or when "Refresh Now" runs), not per-render — cheap.

### Filters on the tab

- Time range: All-time / Last 30 days / Last 7 days
- Min sample size: drop slices with < N rows so a 1-row outlier doesn't claim "best ever"

### Drill behavior

Click any "Best" or "Worst" cell → drill modal showing the rows from that specific date/city/category combo, with the metric value highlighted.

### Files to add/modify

- `Task_Efficiency_Dashboard.html`:
  - Add new tab `<div class="report-tab" onclick="switchReport('benchmarks',this)"><span class="tab-num">8</span>Benchmarks</div>`
  - Add new page `<div class="report-page" id="page-benchmarks">...</div>`
  - Add `renderBenchmarksPage()` function
  - Add `computeBenchmarks()` helper (runs once, caches result)
  - Wire into `rerender()` and `switchReport()`

### Verification

1. Open Benchmarks tab → 4 sections render
2. Click "Done % Best" for Bangalore → drill shows the day with highest Done % in that city, with all rows from that day
3. Recommended Green Threshold for FSD% (p75 of all slices) → matches a manual percentile calc in Excel from raw data dump
4. Toggle "Last 7 days" filter → numbers shrink to 7-day window, recompute correctly

### Open questions

1. **Tab name** — Benchmarks / Records / Performance Range / Thresholds?
2. **Time range default** — All-time, last 30 days, or last 7 days?
3. **Min sample size** — drop slices with fewer than N rows (suggest N=10)?
4. **Thresholds replacement** — should the existing `CA_THRESHOLDS` (`{fad:80, fsd:60, task:90, tat:50}`) auto-update from p75 values, or stay manual with these as suggestions?
5. **Drill behavior** — drill into the SPECIFIC day that achieved the best/worst, or into all rows matching that city+category over the whole period?
