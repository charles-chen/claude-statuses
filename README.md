# claude-statuses

Uptime history for [status.claude.com](https://status.claude.com), inspired by [mrshu's GitHub status page](https://mrshu.github.io/github-statuses/).

**Live site:** https://YOUR_USERNAME.github.io/claude-statuses/

---

## How it works

Anthropic's status page shows current incidents but doesn't expose aggregate uptime numbers. This project reconstructs them by archiving incident data and computing per-component uptime over rolling windows (30d, 90d, all-time).

A GitHub Action polls the Statuspage API every hour and commits snapshots to `data/all_incidents.json`. `scripts/build.py` replays all incident updates per component, reconstructs downtime windows, merges overlaps, and writes `data/uptime.json`. The frontend is a single `index.html` that reads that file — no build step, no framework.

Historical data goes back to March 2023, backfilled via Playwright scraping of the history pages.

---

## Local development

```bash
python scripts/fetch_all_pages.py  # fetch latest incidents
python scripts/build.py            # rebuild uptime.json
python -m http.server 8000         # serve at localhost:8000
```
