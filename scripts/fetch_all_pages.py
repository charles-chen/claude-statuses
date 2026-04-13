#!/usr/bin/env python3
"""
Fetch all pages of incidents from the Statuspage API and merge into
data/all_incidents.json. Run once to bootstrap, then hourly archiving
keeps it up to date.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://status.claude.com/api/v2/incidents.json"
OUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "all_incidents.json")

def fetch_page(page: int) -> list:
    url = f"{BASE_URL}?page={page}&per_page=100"
    req = urllib.request.Request(url, headers={"User-Agent": "claude-status-uptime/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("incidents", [])

def main():
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)

    # Load existing incidents so we don't lose anything
    existing = {}
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE) as f:
            for inc in json.load(f):
                existing[inc["id"]] = inc

    page = 1
    fetched = 0
    while True:
        print(f"Fetching page {page}...")
        incidents = fetch_page(page)
        if not incidents:
            break
        for inc in incidents:
            existing[inc["id"]] = inc
        fetched += len(incidents)
        if len(incidents) < 100:
            break
        page += 1

    print(f"Fetched {fetched} incidents across {page} pages. Total unique: {len(existing)}")

    all_incidents = sorted(existing.values(), key=lambda x: x["started_at"], reverse=True)
    with open(OUT_FILE, "w") as f:
        json.dump(all_incidents, f, separators=(",", ":"))
    print(f"Wrote {len(all_incidents)} incidents to {OUT_FILE}")

if __name__ == "__main__":
    main()
