#!/usr/bin/env python3
"""
Reads data/all_incidents.json and computes per-component uptime statistics,
writing results to data/uptime.json for the static frontend to consume.

Uptime is computed by:
1. For each component, collect all downtime windows from incident_updates
   (where new_status != 'operational').
2. Merge overlapping windows.
3. Compute uptime % = 1 - (total_downtime / window_duration).

Windows computed: last 30d, last 90d, all-time.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INCIDENTS_FILE = os.path.join(DATA_DIR, "all_incidents.json")
OUT_FILE = os.path.join(DATA_DIR, "uptime.json")

# Canonical component ordering
COMPONENTS = [
    {"id": "rwppv331jlwc", "name": "claude.ai"},
    {"id": "0qbwn08sd68x", "name": "platform.claude.com"},
    {"id": "k8w3r06qmzrp", "name": "Claude API (api.anthropic.com)"},
    {"id": "yyzkbfz2thpt", "name": "Claude Code"},
    {"id": "0scnb50nvy53", "name": "Claude for Government"},
]
COMPONENT_IDS = {c["id"] for c in COMPONENTS}

NON_OPERATIONAL = {"degraded_performance", "partial_outage", "major_outage"}


def parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    # Statuspage uses ISO 8601 with fractional seconds
    s = s.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def merge_windows(windows: list[tuple]) -> list[tuple]:
    """Merge overlapping (start, end) tuples."""
    if not windows:
        return []
    windows = sorted(windows, key=lambda w: w[0])
    merged = [windows[0]]
    for start, end in windows[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def downtime_seconds_in_window(
    windows: list[tuple], window_start: datetime, window_end: datetime
) -> float:
    total = 0.0
    for start, end in windows:
        # Clip to window
        s = max(start, window_start)
        e = min(end, window_end)
        if e > s:
            total += (e - s).total_seconds()
    return total


def extract_downtime_windows(incidents: list, component_id: str) -> list[tuple]:
    """
    For each incident, reconstruct when a component was non-operational
    by walking incident_updates in chronological order.
    """
    windows = []
    for incident in incidents:
        updates = sorted(
            incident.get("incident_updates", []),
            key=lambda u: u["created_at"],
        )

        down_start = None
        for update in updates:
            affected = update.get("affected_components") or []
            for comp in affected:
                if comp.get("code") != component_id:
                    continue
                new_status = comp.get("new_status", "operational")
                old_status = comp.get("old_status", "operational")
                ts = parse_dt(update["created_at"])
                if ts is None:
                    continue

                if new_status in NON_OPERATIONAL and down_start is None:
                    down_start = ts
                elif new_status == "operational" and down_start is not None:
                    windows.append((down_start, ts))
                    down_start = None

        # If incident resolved but we never saw a recovery update for this component,
        # use resolved_at as end
        if down_start is not None:
            resolved = parse_dt(incident.get("resolved_at"))
            if resolved:
                windows.append((down_start, resolved))
            # else: still ongoing — use now
            else:
                windows.append((down_start, datetime.now(timezone.utc)))

    return windows


def uptime_pct(downtime_s: float, window_s: float) -> float:
    if window_s <= 0:
        return 100.0
    return round((1 - downtime_s / window_s) * 100, 3)


def main():
    if not os.path.exists(INCIDENTS_FILE):
        print(
            f"No incidents file found at {INCIDENTS_FILE}. Run fetch_all_pages.py first."
        )
        return

    with open(INCIDENTS_FILE) as f:
        incidents = json.load(f)

    now = datetime.now(timezone.utc)
    windows_def = {
        "30d": (now - timedelta(days=30), now),
        "90d": (now - timedelta(days=90), now),
        "all": (None, now),  # None = use earliest incident
    }

    # Find earliest incident for all-time window
    all_starts = [
        parse_dt(inc["started_at"]) for inc in incidents if inc.get("started_at")
    ]
    earliest = min(all_starts) if all_starts else now - timedelta(days=365)
    windows_def["all"] = (earliest, now)

    results = []
    for comp in COMPONENTS:
        cid = comp["id"]
        raw_windows = extract_downtime_windows(incidents, cid)
        merged = merge_windows(raw_windows)

        comp_result = {
            "id": cid,
            "name": comp["name"],
            "uptime": {},
            "incidents": [],
        }

        for label, (wstart, wend) in windows_def.items():
            window_s = (wend - wstart).total_seconds()
            down_s = downtime_seconds_in_window(merged, wstart, wend)
            comp_result["uptime"][label] = uptime_pct(down_s, window_s)

        # Recent incidents for this component (last 90d, max 10)
        cutoff = now - timedelta(days=90)
        recent = []
        for inc in incidents:
            started = parse_dt(inc.get("started_at"))
            if started and started < cutoff:
                continue
            # Check if this component was affected
            affected_ids = set()
            for update in inc.get("incident_updates", []):
                for comp_ref in update.get("affected_components") or []:
                    affected_ids.add(comp_ref.get("code"))
            if cid not in affected_ids:
                continue
            recent.append(
                {
                    "id": inc["id"],
                    "name": inc["name"],
                    "impact": inc.get("impact", "none"),
                    "started_at": inc.get("started_at"),
                    "resolved_at": inc.get("resolved_at"),
                    "status": inc.get("status"),
                }
            )
            if len(recent) >= 10:
                break

        comp_result["incidents"] = recent
        results.append(comp_result)
        print(
            f"{comp['name']}: 30d={comp_result['uptime']['30d']}%  90d={comp_result['uptime']['90d']}%  all={comp_result['uptime']['all']}%"
        )

    # Aggregate: minimum uptime across all components per window
    aggregate = {
        label: min(r["uptime"][label] for r in results)
        for label in ("30d", "90d", "all")
    }
    print(
        f"Aggregate (min): 30d={aggregate['30d']}%  90d={aggregate['90d']}%  all={aggregate['all']}%"
    )

    output = {
        "generated_at": now.isoformat(),
        "components": results,
        "aggregate": aggregate,
        "earliest_data": earliest.isoformat(),
    }

    with open(OUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote uptime data to {OUT_FILE}")


if __name__ == "__main__":
    main()
