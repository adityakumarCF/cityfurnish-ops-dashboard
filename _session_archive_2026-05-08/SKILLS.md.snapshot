# SKILLS.md — CityFurnish Dashboard Workflows

Reusable patterns for working on this dashboard. Full version with code examples lives at `_session_archive_2026-05-08/SKILLS.md`. This is the quick reference.

---

## Adding a new comparison table on KPI Trend

Use `compCard9`. Build a `mrows` array via `mRow(label, vA, vB, v7, v30, isPct, hb, dec, metricKey)`, then pass to `compCard9(title, mrows, firstColLabel)`.

`hb`:
- `true` — higher is better
- `false` — lower is better
- `null` — no judgement (raw count)

Verdict + insight strip auto-update.

---

## Drill conventions

`ktDrill(metricKey, dateSpec, label, evt)` — generic.
`ktDrillCityCat(metricKey, cat, city, dateSpec, label, evt)` — city × category cells (Leaders).

`metricKey` shape: `<family>_<sub>_<arg>`. See SKILLS.md in archive for full list.

---

## Reschedule predicate (use everywhere)

```js
r[idx.FSD] === 'False' || r[idx.FSD] === 'NoFS'
```
Same predicate as FSD Missed.

---

## Adding a new city

1. JS: update `CITIES_ALLOWED`
2. Python: update `ALLOWED_CITIES`
3. Verify Metabase has rows for that city

---

## Adding a new tab

1. Add `<div class="report-tab">` to nav
2. Add `<div class="report-page">` page anchor
3. Add tab key to `tvState`, `tvOffset`, `calDates`, `citySelection` JS init
4. Add tab key to Python `cd_new` regeneration line in `refresh_from_metabase.py` (otherwise calDates falls back on next refresh)
5. Add `if(report==='<key>') render<Key>Page();` in `rerender()`
6. Add render function

---

## Deploying

```bash
git add <file>
git commit -m "..."
git pull --rebase
git push origin main
# Pages deploys in 30-60s, hard-refresh browser
```

---

## Local testing

```bash
python -m http.server 8765
# Open http://localhost:8765/Task_Efficiency_Dashboard.html
# Bypass password in DevTools console:
# sessionStorage.setItem('dashAuth','ok'); document.getElementById('password-gate').remove();
```

---

## Validating JS syntax

```bash
node -e "
const fs=require('fs');const html=fs.readFileSync('Task_Efficiency_Dashboard.html','utf8');
const re=/<script[^>]*>([\s\S]*?)<\/script>/gi;let m,i=0;
while((m=re.exec(html))!==null){if(m[1].length>1000){try{new Function(m[1]);console.log('Block',i,'OK');}catch(e){console.log('Block',i,'FAIL:',e.message.split('\n')[0]);}}i++;}
"
```

---

## Don't replace, augment

When the user says "add X", they mean add X. **Not** "redesign to incorporate X".

Default behavior:
1. Sketch the change in text
2. Share a mockup if visual
3. Wait for explicit approval
4. Build additively

---

## When OneDrive locks the file

Edit returns `EUNKNOWN`. `sleep 3` and retry.

---

## Founder-friendly visual conventions

| Cue | Meaning |
|---|---|
| ▲ green | Improving |
| ▼ red | Declining |
| ↔ orange | Mixed |
| ▬ grey | Flat / no judgement |
| 🏆 | Leader cell |
| ⚠ orange chip | Alert / "X of Y" |
| 📍 | Insight strip header |
| Heat tint (cell) | green=better, red=worse, orange=mixed vs reference windows |

Use sparingly — too much color = no signal.
