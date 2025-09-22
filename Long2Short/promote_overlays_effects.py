#!/usr/bin/env python3
"""
Promote per-overlay 'effect' values into the queue entry's top-level 'effects'/'effect'.
Usage:
  python promote_overlays_effects.py "C:\\path\\to\\overlays_queue_....json"
"""
import sys, json, shutil, datetime, os

if len(sys.argv) < 2:
    print("Usage: python promote_overlays_effects.py <overlays_queue.json>")
    sys.exit(2)

qpath = os.path.abspath(sys.argv[1])
if not os.path.isfile(qpath):
    print("Queue file not found:", qpath)
    sys.exit(3)

bak = qpath + ".bak." + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
shutil.copy2(qpath, bak)
print("Backup written to:", bak)

with open(qpath, "r", encoding="utf-8") as f:
    jd = json.load(f)

entries = jd.get("entries", [])
changed = []
for i, ent in enumerate(entries):
    top_effects = ent.get("effects") or []
    top_effect = ent.get("effect") or ""
    if top_effects or top_effect:
        continue
    # scan overlay_textN fields for an 'effect' key
    found = None
    for k, v in list(ent.items()):
        if k.startswith("overlay_text") and isinstance(v, dict):
            e = v.get("effect")
            if e:
                found = e
                break
    if found:
        ent["effects"] = [found]
        ent["effect"] = found
        changed.append((i, found))

if not changed:
    print("No changes required (no per-text effects found or top-level effects already present).")
else:
    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(jd, f, ensure_ascii=False, indent=2)
    print("Updated queue saved. Promoted effects for entries:")
    for idx, eff in changed:
        print(f" - entry {idx}: {eff}")
print("Done.")