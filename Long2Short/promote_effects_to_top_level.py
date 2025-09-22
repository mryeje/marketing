#!/usr/bin/env python3
"""
Promote overlay_instructions.effects into top-level effect/effects so l2s_overlays
(seems to) pick them up. Adds conservative default timing if missing.

Usage:
  python promote_effects_to_top_level.py "C:\path\to\overlays_queue_....json"
"""
import sys, os, json, shutil, datetime

DEFAULT_START = 0.0
DEFAULT_DURATION = 2.5

def promote(qpath):
    qpath = os.path.abspath(qpath)
    if not os.path.isfile(qpath):
        print("Queue file not found:", qpath)
        return 2
    with open(qpath, "r", encoding="utf-8") as f:
        j = json.load(f)

    entries = j.get("entries", [])
    if not entries:
        print("No entries found. Nothing to do.")
        return 0

    changed = False
    for ent in entries:
        oi = ent.get("overlay_instructions", {}) or {}
        oi_effects = oi.get("effects") or []
        # If top-level effects already present and non-empty, skip
        if ent.get("effects"):
            continue
        if not oi_effects:
            # nothing to promote
            continue

        # ensure timing keys exist on each effect dict
        for e in oi_effects:
            if isinstance(e, dict):
                if not any(k in e for k in ("timing", "start", "duration", "begin", "end")):
                    e.setdefault("start", float(DEFAULT_START))
                    e.setdefault("duration", float(DEFAULT_DURATION))

        # copy to top-level
        ent["effects"] = oi_effects
        # set top-level single 'effect' to the first name if not set
        if not ent.get("effect"):
            first_name = ""
            if isinstance(oi_effects, list) and oi_effects:
                first = oi_effects[0]
                if isinstance(first, dict):
                    first_name = first.get("name") or first.get("effect") or ""
                else:
                    first_name = str(first)
            if not first_name:
                # fallback to overlay_instructions.effect
                first_name = oi.get("effect","") or ""
            if first_name:
                ent["effect"] = first_name
        changed = True

    if not changed:
        print("No changes needed (top-level effects already present or none to promote).")
        return 0

    # backup
    bak = qpath + ".bak." + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(qpath, bak)
    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=2)
    print("Updated queue written. Backup at:", bak)
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python promote_effects_to_top_level.py <queue.json>")
        sys.exit(2)
    sys.exit(promote(sys.argv[1]))