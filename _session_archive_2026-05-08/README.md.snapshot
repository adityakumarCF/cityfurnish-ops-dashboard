# Trip Operations Dashboard

Live ops dashboard, fed automatically from Metabase card 280 ("trips data query").

**Live URL:** `https://<your-username>.github.io/<repo-name>/` (set after first Pages deployment)

**Refresh cadence:** every 30 minutes (auto). Manual refresh: see below.

---

## How the pipeline works

```
Metabase card 280 ──► refresh_from_metabase.py ──► Task_Efficiency_Dashboard.html ──► GitHub Pages
       (live)         (transforms shape)            (embedded JSON updated)            (your team's URL)
```

A GitHub Action runs every 30 min:
1. Pulls fresh rows from Metabase using the API key (stored as a repo secret — never in source).
2. Transforms them: applies `mCat`, derives Done flag, computes FSD/VehicleType/etc.
3. Filters out rows scheduled today or later (data is "current day − 1").
4. Replaces the embedded JSON blobs in `Task_Efficiency_Dashboard.html`.
5. Updates date pickers, "Last updated" header timestamp, calendar default.
6. Commits + pushes. GitHub Pages auto-deploys within ~1 minute.

---

## One-time setup

### 1. Create a new GitHub repo
- Name suggestion: `cityfurnish-ops-dashboard`
- **Public** (required for free GitHub Pages on personal accounts)

### 2. Push these files to the repo
From a fresh clone of the empty repo:
```bash
cd /path/to/your/clone
cp -r "C:\Users\User\OneDrive - Default Directory\Documents\Ops_Reports"/* ./
# Or just point your local repo at this folder
git add .
git commit -m "Initial dashboard + refresh pipeline"
git push origin main
```

### 3. Add the three secrets (Repo → Settings → Secrets and variables → Actions → New repository secret)

| Secret name | Value |
|---|---|
| `METABASE_URL` | `https://analytics.rentofurniture.com` |
| `METABASE_API_KEY` | (your Metabase API key — generated in Metabase Settings → API Keys) |
| `METABASE_CARD_ID` | `280` |

### 4. Enable GitHub Pages (Repo → Settings → Pages)
- Source: **GitHub Actions** (not "Deploy from branch")
- The `deploy-pages.yml` workflow handles the rest

### 5. Verify
- Repo → Actions tab → "Refresh dashboard from Metabase" → click **Run workflow** to trigger immediately
- Once green, your URL `https://<user>.github.io/<repo>/` will serve the dashboard
- The header should show "Updated <timestamp>" reflecting the just-now run

---

## How to manually refresh (3 ways)

1. **From the dashboard** — click the "🔄 Refresh Now" button in the header (uses GitHub's API; takes ~1 min). *Requires the API URL configuration in the dashboard — see "Refresh button" below.*
2. **From GitHub** — Repo → Actions → "Refresh dashboard from Metabase" → Run workflow.
3. **From the command line** —
   ```bash
   gh workflow run scheduled-refresh.yml
   ```

---

## Data privacy note ⚠️

Your dashboard is on **public GitHub Pages**. Anyone with the URL can view all customer / agent / vehicle data. Treat the URL as a "weak secret":

- Share via Slack/email only with the ops team
- Don't post in public docs, social media, or screenshots
- Don't commit it to other public repos
- If the URL ever leaks, rotate by:
  1. Renaming the repo (changes the URL)
  2. Or making the repo private and stopping Pages

For stronger protection (per-user email allowlist), upgrade to Cloudflare Pages + Access (free, ~15 min migration).

---

## File map

| File | Purpose |
|---|---|
| `Task_Efficiency_Dashboard.html` | The dashboard. Self-contained — embeds the data. |
| `refresh_from_metabase.py` | Pulls Metabase card 280, rewrites the embedded blobs in the HTML. |
| `.github/workflows/scheduled-refresh.yml` | Cron + manual trigger for the refresh job. |
| `.github/workflows/deploy-pages.yml` | Auto-deploys to GitHub Pages on push to `main`. |
| `.gitignore` | Excludes secrets, raw xlsx files, and old artifacts. |

---

## Troubleshooting

**Action fails with "401 Unauthorized" from Metabase**
- Check `METABASE_API_KEY` secret is set and the key is still valid
- Generate a new key in Metabase → Settings → API Keys
- Confirm the key's user has access to card 280

**Action fails with "required columns missing"**
- Card 280's columns must include: Status, City, Job Type, Scheduled Date, Order Id (at minimum)
- Optional but expected: first Schedule Date, Adhoc Vehicle, Transport, Agent Name, Ticket Number, Deliver Date
- If column names changed in Metabase, edit `find_col(...)` calls in `refresh_from_metabase.py` to add aliases

**Dashboard shows old data**
- Check Actions tab — did the latest run succeed?
- Browser cache: hard reload (Ctrl+Shift+R)
- GitHub Pages cache: usually clears within 1-2 min of deploy

**Refresh script runs locally but not in Action**
- Compare local env vars vs Action secrets — names must match exactly
- Action logs (Actions tab → click the run) show every step's output
