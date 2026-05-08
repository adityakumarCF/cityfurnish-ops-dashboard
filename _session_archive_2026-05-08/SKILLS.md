# Skills — Workflows for the CityFurnish Dashboard

Reusable patterns and workflows established this session.

---

## Skill: Adding a new comparison table on KPI Trend

**Pattern:** Use the unified `compCard9` component. Build a `mrows` array, pass to `compCard9`.

```js
// Inside renderKpiTrendPage()
var myMrows = [];
myMrows.push(mRow(
  'My Metric Label',           // label (or city/JT name)
  valToday,                    // vA — selected day value
  valYesterday,                // vB — yesterday value
  val7dAvg,                    // v7 — 7-day window average
  val30dAvg,                   // v30 — 30-day window average
  true,                        // isPct — append '%' / 'pp'?
  true,                        // hb — higher better? (true / false / null)
  undefined,                   // dec — decimal places (defaults: 1 for pct, 0 for ints)
  'metric_key_for_drill'       // metricKey — drives ktDrill() filter; pass undefined if no drill
));
// ... more rows ...

// Render with section name + first column label
secX += compCard9('My table title', myMrows, 'City');  // or 'Metric' or 'Job Type'
```

**Verdict & insight strip auto-update.** Don't hand-roll either.

---

## Skill: Drill-down conventions

Every value cell in a comparison table is drillable via `ktDrill(metricKey, dateSpec, label, evt)`.

`metricKey` shape: `<family>_<sub>_<arg>`. Examples:
- `task_total`, `task_done`, `task_notdone`
- `fad_pct_overall`, `fad_pct_Delivery`, `fad_count_overall`
- `fsd_pct_overall`, `fsd_true_overall`, `fsd_false_Delivery`
- `tat_within`, `tat_breach`, `tat_done`, `tat_resch`
- `trip_unique`, `trip_single`, `trip_multi`, `trip_waste`

`dateSpec`:
- String YMD (`'2026-05-06'`) → single day
- `[startYMD, endYMD]` → date range (e.g. 7d window)

For city × category drilling (Leaders), use `ktDrillCityCat(metricKey, cat, city, dateSpec, label, evt)`.

---

## Skill: Adding a city to the allowlist

Update **both layers**:

1. **JS** (`Task_Efficiency_Dashboard.html`):
   ```js
   var CITIES_ALLOWED = ["Bangalore","Gurgaon","Hyderabad","Mumbai","Pune","NewCity"];
   var CITIES_ALLOWED_SET = new Set(CITIES_ALLOWED);
   var ALL_CITIES = CITIES_ALLOWED.slice();
   ```

2. **Python** (`refresh_from_metabase.py`):
   ```python
   ALLOWED_CITIES = {'Bangalore', 'Gurgaon', 'Hyderabad', 'Mumbai', 'Pune', 'NewCity'}
   ```

Also verify the new city has rows in Metabase. Otherwise tables show `—`.

---

## Skill: Reschedule count consistency

**Predicate everywhere:** `r[FSD] === 'False' || r[FSD] === 'NoFS'` (FSD Missed = Reschedule).

If a new view shows reschedule counts:
- KPI / aggregation: same predicate as above
- Drill predicate: `preds.push(r => r[idx.FSD]==='False' || r[idx.FSD]==='NoFS')`
- Filter modal: same filter chips on Reschedule Reason Breakdown
- Verify drill row count == aggregated KPI count (no off-by-one)

---

## Skill: Vehicle-days vs unique fleet

| When to use | Code |
|---|---|
| **Done Efficiency, capacity, scoring** | Vehicle-days = `Σ_day unique(vehicles_today_in_city)` |
| **Total fleet count** (rare) | `new Set(allVehicleIds).size` |

Trip city threshold scoring uses vehicle-days. Most "Total Vehicles" KPIs use vehicle-days. The bug fixed this session was FAD/FSD vehicle tables using unique-fleet count → numbers didn't scale weekly/monthly.

---

## Skill: Adding a new tab

1. Add `<div class="report-tab" onclick="switchReport('<key>',this)">...</div>` to nav
2. Add `<div class="report-page" id="page-<key>">...</div>` page anchor
3. Add `<key>` to:
   - `tvState`, `tvOffset`, `calDates` JS init
   - `citySelection` JS init
   - Python `cd_new` regeneration line in `refresh_from_metabase.py`
4. Add `if(report==='<key>') render<Key>Page();` in `rerender()` switch
5. Add filter bar anchor `<div class="filter-bar" id="filter-<key>"></div>` if needed
6. Add render function `render<Key>Page()`

---

## Skill: Deploying changes

```bash
cd "C:/Users/User/OneDrive - Default Directory/Documents/Ops_Reports"
git add Task_Efficiency_Dashboard.html  # or specific files
git commit -m "..."
git pull --rebase                        # absorb auto-refresh data commits
git push origin main                     # GitHub Pages deploys in 30-60s
```

Then hard refresh (Ctrl+Shift+R) to bypass browser cache.

**Note:** Auto-refresh commits only touch data lines (PROCESSED_EXCEL_FULL, etc.). They don't conflict with JS changes.

---

## Skill: Local testing

```bash
cd "C:/Users/User/OneDrive - Default Directory/Documents/Ops_Reports"
python -m http.server 8765 &
# Open http://localhost:8765/Task_Efficiency_Dashboard.html
```

Bypass password in DevTools console:
```js
sessionStorage.setItem('dashAuth','ok'); document.getElementById('password-gate').remove();
```

---

## Skill: Syntax-checking the dashboard JS

The JS is embedded in HTML. Validate with Node:
```bash
node -e "
const fs=require('fs');const html=fs.readFileSync('Task_Efficiency_Dashboard.html','utf8');
const re=/<script[^>]*>([\s\S]*?)<\/script>/gi;let m,i=0;
while((m=re.exec(html))!==null){
  if(m[1].length>1000){
    try{new Function(m[1]);console.log('Block',i,'OK');}
    catch(e){console.log('Block',i,'FAIL:',e.message.split('\n')[0]);}
  }
  i++;
}
"
```

Block 4 should be the giant data+code block (~30 MB). Block 3 is the password gate (~1 KB).

---

## Skill: When OneDrive locks the file

`Edit` returns `EUNKNOWN: unknown error`. Fix:
```bash
sleep 3 && echo ok   # wait for OneDrive to release
```
Then retry the Edit. Usually unblocks within 3 seconds.

---

## Skill: Working with auto-refresh

The Python script regenerates these baked-in JS lines on every run:
- `var PROCESSED_EXCEL_FULL = ...`
- `var RAW_EXCEL = ...`
- `var ITEM_EXCEL_FULL = ...`
- `var ZOHO_REASONS = ...`
- `var calDates = {...}`

If you add a new report tab key, **also update the Python line that emits `calDates`** so the baked-in version includes your new key. Otherwise it falls back to default and the date filter breaks.

---

## Skill: Founder-friendly visual conventions

| Visual cue | When to use |
|---|---|
| ▲ green | Improving (`hb=true` and Δ>0) OR (`hb=false` and Δ<0) |
| ▼ red | Declining (opposite of above) |
| ↔ orange | Mixed deltas across windows |
| ▬ grey | Flat or no judgement |
| 🏆 | Leader cell in a leaderboard |
| ⚠ orange chip | "X of Y" alerts in insight strips |
| 📍 orange tint | Insight strip header |
| Heat-good (green tint) | Cell beats both reference windows |
| Heat-bad (red tint) | Cell below both references |
| Heat-warn (orange tint) | Mixed |

Use sparingly — too much color = no signal.

---

## Skill: Don't replace, augment

**Lesson learned this session.** When the user says "add X", they don't mean "redesign the whole tab". Add the new section, leave the rest alone, and confirm placement before any structural changes.

If unsure whether a request implies replacement:
1. Sketch the change in plain text
2. Share the design (mockup HTML if visual)
3. Wait for explicit approval
4. Then build

Iterations 1-3 in this session were lost work because of redesigning instead of augmenting.
