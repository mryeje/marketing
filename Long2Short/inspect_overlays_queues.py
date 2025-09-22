#!/usr/bin/env python3
"""
Inspect all overlays_queue_*.json files in a directory and print counts + first entry.
Usage:
  python inspect_overlays_queues.py              # uses ./clips by default
  python inspect_overlays_queues.py "C:\path\to\clips"
"""
import os, json, sys, glob, datetime

def inspect_dir(clips_dir):
    pattern = os.path.join(clips_dir, "overlays_queue_*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        print("No overlays_queue_*.json files found in", clips_dir)
        return 1
    for p in files:
        try:
            st = os.stat(p)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).isoformat()
            size_kb = st.st_size / 1024.0
            print("="*80)
            print("File:", p)
            print(f"  size: {size_kb:.1f} KB    modified: {mtime}")
            with open(p, "r", encoding="utf-8") as f:
                j = json.load(f)
            entries = j.get("entries") or []
            print("  entries:", len(entries))
            if entries:
                first = entries[0]
                print("\n--- first entry keys ---")
                for k in list(first.keys()):
                    print(" ", k)
                ov = first.get("overlay_instructions") or first.get("overlay_instructions", {})
                print("\n--- overlay_instructions (first entry) ---")
                print(json.dumps(ov, ensure_ascii=False, indent=2))
            else:
                print("  (no entries)")
        except Exception as e:
            print("Failed to inspect", p, ":", e)
    print("="*80)
    return 0

if __name__ == "__main__":
    clips_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "clips")
    if not os.path.isdir(clips_dir):
        print("Clips directory not found:", clips_dir)
        sys.exit(2)
    sys.exit(inspect_dir(clips_dir))