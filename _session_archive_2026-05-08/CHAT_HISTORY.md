# Session Chat History — 2026-05-08

Chronological record of work on the CityFurnish Operations Dashboard.
Project root: `C:\Users\User\OneDrive - Default Directory\Documents\Ops_Reports\`
Deployed at: https://adityakumarcf.github.io/cityfurnish-ops-dashboard/Task_Efficiency_Dashboard.html

---

## Session arc

The session covered an extended evolution of the **KPI Trend** tab and several supporting fixes across the dashboard. Themes:
1. Drill-down consistency for unwired metrics (FAD/FSD/Top Offenders/Multi-trip drills)
2. Reschedule count alignment across TAT / KPI Trend / FSD pages
3. City allowlist enforcement (5 cities: Bangalore, Gurgaon, Hyderabad, Mumbai, Pune)
4. Weekly/monthly view bug fixes (silently broken)
5. FAD/FSD vehicle-days correction (vehicle-days vs unique fleet count)
6. KPI Trend tab redesign (multiple iterations, see below)
7. City × Category Leaders section build
8. Final unification of comparison-table format across all KPI Trend sub-sections

---

## Key business logic decisions reinforced this session

| Concept | Definition |
|---|---|
| **FAD** | First Attempt Delivery — order is Done AND its OID is unique. Pickup uses rolling 2-month window (previous month start → max scheduled date). Delivery / SR use full history. |
| **FSD** | First Schedule Done — `True` if Done AND `sd <= ref` (where ref = Requested Date else First Schedule Date), `False` if Done late, `NoFS` if Pending (no first-schedule reference). |
| **Reschedule** | Same predicate as **FSD Missed** = `FSD ∈ {'False', 'NoFS'}`. Pending counts as rescheduled because the commitment date was missed. Unified across TAT page, KPI Trend, FSD page, drill modals, Reschedule Reason Breakdown, Top Offenders. |
| **Vehicle-days** | Each vehicle counted once per working day (not unique fleet count). Used in city threshold scoring, capacity tables. Days that are Thursdays are excluded (operational holiday). |
| **Done Efficiency** | Done tasks ÷ vehicle-days. |
| **Allowed cities** | `Bangalore, Gurgaon, Hyderabad, Mumbai, Pune` only. Chennai/Hosur/Jaipur/Nasik filtered out at multiple layers (Python ALLOWED_CITIES, JS CITIES_ALLOWED, ITEM_DATA loop, Benchmark). |
| **Excluded job types** | `PO Payment, Stock Transfer, Refurb Transfer` — filtered during Python build. |
| **Thursday exclusion** | `isThursdayYMD()` — skipped from all aggregation predicates. |

---

## KPI Trend tab — full evolution (this session)

### Iteration 1 — Dynamic 7d/30d windows (rejected)
First built dynamic sliding 7d/30d windows from selected date with:
- Trend Verdict chip strip at top
- Replaced "vs yesterday" with "vs 7d / vs 30d"
- City × Category Leaders section
- All KPI cards redesigned

**User feedback:** Reverted everything except City × Category Leaders. Said don't replace existing KPI/Trip/TAT sections, only add new things.

### Iteration 2 — Restore originals + keep only Leaders
Restored original `renderKpiTrendPage` (Day vs Yesterday + 7d Avg) and kept only the City × Category Leaders section between KPI Snapshot and Trip Efficiency.

### Iteration 3 — Move Leaders to top, remove static KPI strips, fix bullet
- Reordered HTML anchors so Leaders renders first
- Removed redundant 5-card kpi-strip from KPI Snapshot, Trip Efficiency, TAT Comparison sections (those KPIs already exist on dedicated tabs)
- Fixed invisible Leaders title bullet (was using undefined `var(--blue)` → switched to `var(--orange)`)

### Iteration 4 — Option B + insight strip (current state)
Final design (after sharing UI mockup `kpi-trend-table-samples.html` and getting Option B + insight-strip approval):

Each comparison table now shows:
`Metric | Day | Yesterday | 7d Avg | 30d Avg | Δ d-1 | Δ 7d | Δ 30d | Verdict`

- **Verdict pill** logic: all 3 deltas in improving direction → `▲ Improving` (green); all 3 declining → `▼ Declining` (red); mixed → `↔ Mixed` (orange); zero → `▬ Flat`.
- **Heat tint on Day cell**: green if Day beats both averages, red if below both, orange if mixed.
- **Coloured deltas**: ▲ green / ▼ red, auto-flipped for "lower-is-better" metrics (Reschedule, Multi-trip, Waste, Adhoc%, Breach, Avg TAT, Reschedule rate).
- **Auto insight strip per table** — biggest drop (vs 30d preferred), biggest gain, "X of Y declining · Z improving".
- All cells drillable to underlying rows for the matching window.

### Iteration 5 — Unified table format (root-cause fix)
**Root cause:** Two parallel table components (`compCard9` 9-col + insight strip, `custCard` 5-8 col without insight strip) caused inconsistent format and missing insight strips on city/JT breakdown tables.

**Fix at component level:**
- Single component `compCard9` now drives every comparison table
- Added `firstColLabel` parameter so it renders 'Metric', 'City', or 'Job Type' as first column header
- Trip section now has 3 compCard9 tables: Trip metrics + Single-trip % by city + Avg trips/order by job type
- TAT section now has 3 compCard9 tables: Overall TAT metrics + Within TAT % by city + Within TAT % by job type
- Removed all `custCard` usage in Trip/TAT renders
- City × Category Leaders deliberately untouched (uses `custCard` for matrix layout, different shape)

---

## Other fixes shipped this session

| Fix | Description |
|---|---|
| Reschedule count alignment | All paths use `FSD ∈ {'False','NoFS'}` predicate. Drill-down rows match KPI counts everywhere. |
| FAD/FSD vehicle table scaling | Used `.size` of unique vehicle Set instead of vehicle-days. Switched to `vdReg/vdAdh/vdTot` to match Task tab. Weekly/monthly counts now scale correctly. |
| Tab slider stuck on Action Needed | `positionSlider` used `getBoundingClientRect` when `seg-tray` was overflow-clipped. Switched to `offsetLeft/offsetWidth` (parent-relative). |
| Weekly/monthly silently broken | `iVeh[city]` TypeError because `iVeh` only initialized for 5 allowed cities while `ITEM_EXCEL_FULL` still had Chennai/Hosur rows. Fixed by adding `if(!CITIES_ALLOWED_SET.has(city))return;` skip in ITEM_DATA loop. |
| KPI Trend reschedule mismatch (63 vs 88) | `calDates['kpitrend']` was missing → fell back to default May 2 instead of May 7. Fixed by adding all 10 report keys to both JS init and Python regeneration. |
| Filter label styling | `.filter-label` CSS was scoped to `.filter-bar .filter-label`. Made it global. |
| Pill heights mismatch | Different padding/icon sizes. Unified to `height:24px;box-sizing:border-box`. |
| Missing FSD pill | Built amber pill in FSD view bar with click-to-modal (Option A+B from `missing-fsd-samples.html` mockup). |
| Benchmark tab | Built single-screen comparison view with 3 single-select filters, theme-matched colors, no purple. City restriction enforced. ALL_CITIES kept fixed (never rebuilt from row data). |

---

## Critical files

### Main dashboard
`Task_Efficiency_Dashboard.html` — 30 MB single-page app (data baked in)
- Sections: Overview · Task · FAD · FSD · TAT · Trip · KPI Trend · Benchmark · Action Needed · Simplified
- Password gate: `cf@admin`
- Data globals: `PROCESSED_EXCEL_FULL`, `RAW_EXCEL`, `ITEM_EXCEL_FULL`, `ZOHO_REASONS`
- City filter: `citySelection` per-report Set, `CITIES_ALLOWED` constant array

### Python refresh
`refresh_from_metabase.py` — pulls from Metabase + Mongo, writes processed data into HTML
- Auto-runs via GitHub Actions `scheduled-refresh.yml`
- Triggered by "Refresh Now" button → Cloudflare Worker → GitHub workflow_dispatch

### Cloudflare Worker
`cloudflare-worker.js` — proxy for refresh trigger + Zoho reschedule reasons
- KV namespace: `RESCH_REASONS` (binding: `RESCH_KV`)
- Routes: `POST /` (trigger refresh), `GET /` (poll status), `POST /zoho-webhook`, `GET /zoho-reasons`

### Plan files
`_session_archive_2026-05-08/plans/plan-cbm-and-benchmarks.md` — CBM utilization + Missing FSD + Benchmarks tab plan (deferred items)

---

## Deployment workflow

1. Edit `Task_Efficiency_Dashboard.html` (or any source)
2. `git add` → `git commit` → `git pull --rebase` → `git push origin main`
3. GitHub Pages picks up in 30–60s
4. Hard refresh browser (Ctrl+Shift+R) to bypass cache
5. Auto-refresh of Metabase data runs separately via scheduled workflow — those commits won't conflict because they only modify data lines, not JS

---

## Open / deferred items (not done this session)

- CBM capacity utilization view (founder will provide product CBM master + vehicle CBM map)
- Item-level KPI views beyond Task Efficiency tab
- Benchmark tab — Performance Range / Records analysis (built but lighter scope than originally planned)
- Streaks / percentile rank in KPI Trend (skipped for performance)
