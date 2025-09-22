#!/usr/bin/env python3
"""
Add default timing to overlay_instructions.effects entries that lack timing.
Usage:
  python add_default_timing_to_queue.py "C:\path\to\overlays_queue_...json"

This script:
- Makes a timestamped backup of the queue file.
- Adds default start/duration to any effects entries that don't have timing.
"""
import sys, json, shutil, datetime, os

def add_defaults(qpath, default_start=0.0, default_duration=2.5):
    qpath = os.path.abspath(qpath)
    with open(qpath, "r", encoding="utf-8") as f:
        j = json.load(f)
    entries = j.get("entries", [])
    changed = False
    for ent in entries:
        oi = ent.setdefault("overlay_instructions", {})
        effs = oi.setdefault("effects", [])
        for e in effs:
            if not isinstance(e, dict):
                continue
            # Accept several possible timing key names; add defaults if none present
            if not any(k in e for k in ("timing", "start", "duration", "begin", "end")):
                e.setdefault("start", float(default_start))
                e.setdefault("duration", float(default_duration))
                changed = True
    if not changed:
        print("No changes needed.")
        return
    # backup
    bak = qpath + ".bak." + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(qpath, bak)
    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=2)
    print("Updated queue written, backup at:", bak)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_default_timing_to_queue.py <queue.json>")
        sys.exit(2)
    add_defaults(sys.argv[1])