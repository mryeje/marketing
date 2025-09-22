#!/usr/bin/env python3
"""
Small utility to insert the _adjust_entries_to_clip helper into an l2s_core.py file.

Usage:
  python insert_adjust_entries.py [path/to/l2s_core.py]

If no path is given, the script looks for l2s_core.py in the current working directory.
The script is idempotent: if the function is already present it will do nothing.
A backup of the original file is written next to it with a .bak.TIMESTAMP suffix.
"""
import sys
import os
import shutil
import time

FUNC_NAME = "_adjust_entries_to_clip"
FUNC_TEXT = """def _adjust_entries_to_clip(srt_entries: list, clip_start_s: float, clip_duration_s: float) -> list:
    \"\"\"
    Convert a list of srt-like entries with absolute 'start' and 'end' seconds
    into clip-relative entries for a trimmed clip.

    Inputs:
      - srt_entries: list of dicts with keys 'start', 'end', 'text' (start/end in seconds, absolute wrt source)
      - clip_start_s: the start time (seconds) of the trimmed clip in the source video
      - clip_duration_s: duration (seconds) of the trimmed clip

    Returns:
      - list of dicts with keys 'start', 'end', 'text' where start/end are
        relative to the clip (0 .. clip_duration_s). Entries that do not
        overlap the clip are omitted. Entries that partially overlap are clipped.
    \"\"\"
    out = []
    if not srt_entries:
        return out
    try:
        for ent in srt_entries:
            if not isinstance(ent, dict):
                continue
            # Safe extraction of start/end as floats (they may be strings)
            try:
                abs_start = float(ent.get(\"start\", 0.0))
            except Exception:
                try:
                    abs_start = float(str(ent.get(\"start\", 0)).strip())
                except Exception:
                    continue
            try:
                abs_end = float(ent.get(\"end\", abs_start))
            except Exception:
                try:
                    abs_end = float(str(ent.get(\"end\", abs_start)).strip())
                except Exception:
                    abs_end = abs_start

            # Compute clip-relative times
            rel_start = abs_start - float(clip_start_s)
            rel_end = abs_end - float(clip_start_s)

            # Clip to clip bounds
            if rel_end <= 0.0:
                # entry ends before clip starts
                continue
            if rel_start >= float(clip_duration_s):
                # entry starts after clip ends
                continue

            rel_start = max(0.0, rel_start)
            rel_end = min(float(clip_duration_s), rel_end)
            if rel_end <= rel_start:
                continue

            text = ent.get(\"text\", \"\") or ent.get(\"caption\", \"\") or \"\"
            # Normalize whitespace
            if isinstance(text, str):
                text = text.strip()
            else:
                text = str(text)

            out.append({\"start\": rel_start, \"end\": rel_end, \"text\": text})
    except Exception:
        # Be defensive: on unexpected formats, return empty list
        return []
    return out
"""

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "l2s_core.py"
    if not os.path.isfile(path):
        print(f"[ERROR] l2s_core.py not found at: {path}")
        sys.exit(2)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if FUNC_NAME in src:
        print(f"[OK] {FUNC_NAME} already present in {path}; no changes made.")
        return

    # Backup original
    ts = int(time.time())
    bak_path = f"{path}.bak.{ts}"
    shutil.copy2(path, bak_path)
    print(f"[INFO] Backed up original to: {bak_path}")

    insert_point = src.find("def process_recipe(")
    if insert_point == -1:
        # fallback: append at end
        new_src = src.rstrip() + "\n\n\n" + FUNC_TEXT + "\n"
        where = "end of file"
    else:
        # Insert before process_recipe definition
        # Ensure we place the function separated by two newlines
        pre = src[:insert_point].rstrip() + "\n\n\n"
        post = src[insert_point:].lstrip()
        new_src = pre + FUNC_TEXT + "\n\n\n" + post
        where = "before def process_recipe"

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"[OK] Inserted {FUNC_NAME} into {path} ({where}).")
    print("You can now re-run your script that called process_recipe.")

if __name__ == "__main__":
    main()