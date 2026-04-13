# claude-status-uptime

Aggregate uptime statistics for [status.claude.com](https://status.claude.com), similar to [mrshu's GitHub status page](https://mrshu.github.io/github-statuses/).

**Live site:** https://YOUR_USERNAME.github.io/claude-status-uptime/

---

## How it works

- **Data source:** Anthropic's public Statuspage API (`/api/v2/incidents.json`)
- **Archiving:** A GitHub Action polls the API every hour and commits snapshots to `data/all_incidents.json`
- **Uptime computation:** `scripts/build.py` replays all incident updates per component, reconstructs downtime windows, merges overlaps, and emits `data/uptime.json`
- **Frontend:** A single static `index.html` reads `data/uptime.json` and renders the table

No NER or ML needed — Statuspage already tags each incident update with affected component IDs and status transitions.

---

## Setup

### 1. Create the repo and enable GitHub Pages

```
gh repo create claude-status-uptime --public
git push -u origin main
```

Then go to **Settings → Pages → Source: GitHub Actions**.

### 2. Bootstrap historical data

```bash
pip install -r requirements.txt  # (none needed, stdlib only)
python scripts/fetch_all_pages.py
python scripts/build.py
git add data/ && git commit -m "chore: bootstrap data" && git push
```

### 3. Let the cron take over

The `archive.yml` workflow runs every hour, fetching new incidents and rebuilding `uptime.json`. The `deploy.yml` workflow redeploys Pages whenever `uptime.json` changes.

---

## Components tracked

| Component | ID |
|---|---|
| claude.ai | `rwppv331jlwc` |
| platform.claude.com | `0qbwn08sd68x` |
| Claude API (api.anthropic.com) | `k8w3r06qmzrp` |
| Claude Code | `yyzkbfz2thpt` |
| Claude for Government | `0scnb50nvy53` |

---

## Uptime windows

| Window | Description |
|---|---|
| 30d | Rolling last 30 days |
| 90d | Rolling last 90 days |
| All time | From earliest available incident |

Downtime windows are merged before computing uptime, so overlapping incidents affecting the same component aren't double-counted.
