#!/usr/bin/env python3
"""
Uses Playwright to scrape status.claude.com/history pages and backfill
older incidents. Playwright renders the JS so we get the full data.

Setup:
    pip install playwright
    playwright install chromium

Usage:
    python scripts/scrape_history.py
"""
import json
import os
import time
import urllib.request

from playwright.sync_api import sync_playwright

OUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "all_incidents.json")
HISTORY_URL = "https://status.claude.com/history"
INCIDENT_URL = "https://status.claude.com/api/v2/incidents/{}.json"
MAX_PAGES = 20


def load_existing() -> dict:
    if not os.path.exists(OUT_FILE):
        return {}
    with open(OUT_FILE) as f:
        return {inc["id"]: inc for inc in json.load(f)}


def save(existing: dict) -> int:
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    all_incidents = sorted(
        existing.values(), key=lambda x: x.get("started_at", ""), reverse=True
    )
    with open(OUT_FILE, "w") as f:
        json.dump(all_incidents, f, separators=(",", ":"))
    return len(all_incidents)


def fetch_incident_detail(incident_id: str):
    try:
        req = urllib.request.Request(
            INCIDENT_URL.format(incident_id),
            headers={"User-Agent": "claude-statuses/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("incident")
    except Exception as e:
        print(f"    Warning: could not fetch detail for {incident_id}: {e}")
        return None


def extract_codes_from_page(page) -> set:
    codes = set()

    # Try reading JS data object directly
    try:
        months = page.evaluate(
            """
            () => {
                const candidates = [window.SD, window.__sd, window.initialData];
                for (const obj of candidates) {
                    if (obj && obj.months) return obj.months;
                    if (obj && obj.page && obj.page.months) return obj.page.months;
                }
                return null;
            }
        """
        )
        if months:
            for month in months:
                for inc in month.get("incidents", []):
                    code = inc.get("code") or inc.get("id")
                    if code:
                        codes.add(code)
            return codes
    except Exception:
        pass

    # Fallback: scrape incident links from DOM
    try:
        links = page.eval_on_selector_all(
            'a[href*="/incidents/"]', "els => els.map(el => el.href)"
        )
        for link in links:
            parts = link.rstrip("/").split("/")
            if parts:
                codes.add(parts[-1])
    except Exception:
        pass

    return codes


def main():
    existing = load_existing()
    print(f"Loaded {len(existing)} existing incidents.")

    all_codes = set()

    print("\nPhase 1: collecting incident codes from history pages...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        consecutive_empty = 0
        for page_num in range(1, MAX_PAGES + 1):
            url = f"{HISTORY_URL}?page={page_num}" if page_num > 1 else HISTORY_URL
            print(f"  Page {page_num}...", end=" ", flush=True)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                print(f"ERROR loading page: {e}")
                break

            codes = extract_codes_from_page(page)
            new_codes = codes - all_codes

            if not codes:
                print("no incidents found")
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    print("  Two consecutive empty pages — stopping.")
                    break
                time.sleep(1)
                continue

            consecutive_empty = 0
            all_codes |= codes
            print(f"{len(codes)} incidents ({len(new_codes)} new)")

            if not new_codes and page_num > 1:
                print("  No new codes — reached end.")
                break

            time.sleep(0.5)

        browser.close()

    print(f"\nFound {len(all_codes)} total incident codes.")

    missing = [c for c in all_codes if c not in existing]
    print(f"\nPhase 2: fetching full details for {len(missing)} new incidents...")

    for i, code in enumerate(missing, 1):
        print(f"  [{i}/{len(missing)}] {code}...", end=" ", flush=True)
        detail = fetch_incident_detail(code)
        if detail:
            existing[detail["id"]] = detail
            print(detail.get("name", "?"))
        else:
            print("skipped")
        time.sleep(0.3)

    total = save(existing)
    print(f"\nDone. Total incidents saved: {total}")

    if existing:
        sorted_incs = sorted(existing.values(), key=lambda x: x.get("started_at", ""))
        print(f"Earliest: {sorted_incs[0].get('started_at', 'unknown')}")
        print(f"Latest:   {sorted_incs[-1].get('started_at', 'unknown')}")


if __name__ == "__main__":
    main()
