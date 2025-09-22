#!/usr/bin/env python3
"""
Promote per-text 'effect' fields into overlay_instructions.effect and overlay_instructions.effects.

Usage:
  python update_overlay_queue_promote_effects.py "C:\path\to\overlays_queue_sharpening-recipe_1758216328.json"

If no argument is provided the script will try to find the most recent overlays_queue_*.json in ../clips.
"""
import sys, os, glob, json, shutil, datetime

def find_latest_queue():
    base = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "clips"))
    pattern = os.path.join(base, "overlays_queue_*.json")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None

def promote_effects_in_entry(entry):
    oi = entry.setdefault("overlay_instructions", {})
    # if effects already present and non-empty, do nothing
    if oi.get("effects"):
        return False

    # search locations where effect may be set
    candidates = []
    # overlay_text: list of dicts
    for idx, ot in enumerate(oi.get("overlay_text", []) or []):
        eff = ot.get("effect") or ot.get("effects")
        if eff:
            candidates.append(("overlay_text", idx, eff))
    # main_text: list of dicts
    for idx, mt in enumerate(entry.get("main_text", []) or []):
        eff = mt.get("effect") or mt.get("effects")
        if eff:
            candidates.append(("main_text", idx, eff))
    # highlight_style / caption_style
    for style_key in ("highlight_style", "caption_style"):
        st = oi.get(style_key) or {}
        eff = st.get("effect") or st.get("effects")
        if eff:
            candidates.append((style_key, None, eff))

    if not candidates:
        return False

    # pick the first candidate
    src, idx, eff = candidates[0]
    # normalize effect string
    if isinstance(eff, list):
        eff_name = eff[0] if eff else ""
    else:
        eff_name = str(eff)

    if not eff_name:
        return False

    # set top-level single effect string (some code may check this)
    oi["effect"] = eff_name

    # build effects list entry (conservative/simple structure)
    effects_list = oi.setdefault("effects", [])
    # if overlay_text index known, reference it; otherwise use style key
    entry_obj = {"name": eff_name}
    if src in ("overlay_text", "main_text") and idx is not None:
        entry_obj["overlay_text_index"] = idx
        entry_obj["source"] = src
    else:
        entry_obj["source_style"] = src

    effects_list.append(entry_obj)
    return True

def main():
    if len(sys.argv) > 1:
        qpath = sys.argv[1]
    else:
        qpath = find_latest_queue()
        if not qpath:
            print("No overlays_queue_*.json found. Provide the path as the first argument.")
            return 2

    qpath = os.path.abspath(qpath)
    if not os.path.isfile(qpath):
        print("Queue file not found:", qpath)
        return 3

    print("Using queue:", qpath)
    with open(qpath, "r", encoding="utf-8") as f:
        j = json.load(f)

    entries = j.get("entries", [])
    if not entries:
        print("Queue has no entries. Nothing to do.")
        return 0

    changed = []
    for i, ent in enumerate(entries):
        try:
            if promote_effects_in_entry(ent):
                changed.append(i)
        except Exception as e:
            print("Failed to process entry", i, ":", e)

    if not changed:
        print("No entries changed. Either effects already present or no per-text effect found.")
        return 0

    # backup
    bak = qpath + ".bak." + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(qpath, bak)
    print("Backup written to", bak)

    # write updated queue
    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=2)

    print("Updated entries:", changed)
    print("Wrote updated queue to", qpath)
    print("Now re-run l2s_overlays.py with --queue pointing to this file (and --keep-temp if you want).")

if __name__ == "__main__":
    sys.exit(main())