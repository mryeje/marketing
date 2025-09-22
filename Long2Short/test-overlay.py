#!/usr/bin/env python3
"""
Quick test to check whether subtitles / overlay entries are being parsed and
to exercise overlay_on_file on a single file so we can capture errors/ffmpeg output.

Usage:
    python test_overlay.py "<path-to-stabilized-clip>" "<path-to-recipe.json>" "<clip_id>"
Example:
    python test_overlay.py "C:\\...\\clips\\02_Removing_the_Blade_Safely.mp4" "recipe.json" "02"
If you don't provide recipe/clip_id, it will prompt for them.
"""
import sys, json, traceback, os
import l2s_core

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_overlay.py <stabilized_clip_path> [recipe.json] [clip_id]")
        return
    clip_path = sys.argv[1]
    recipe_path = sys.argv[2] if len(sys.argv) > 2 else None
    clip_id = sys.argv[3] if len(sys.argv) > 3 else None

    print("Using l2s_core from:", l2s_core.__file__)
    print("FFmpeg available:", bool(__import__('shutil').which("ffmpeg")))

    # If user supplied a recipe, try to find the clip entry and show parsed subtitles
    raw_srt = None
    overlay_instructions = None
    if recipe_path and clip_id:
        try:
            r = l2s_core.load_recipe(recipe_path)
            print("Loaded recipe:", recipe_path)
            for c in r.get("clips", []):
                if str(c.get("id")) == clip_id:
                    print("Found clip entry for id:", clip_id)
                    raw_srt = c.get("subtitles") or c.get("srt_stub")
                    overlay_instructions = c.get("overlay_instructions") or {}
                    break
            if raw_srt is None:
                print("No subtitles key found in clip; trying 'srt_stub' or top-level recipe srt.")
        except Exception:
            print("Failed to load recipe:", traceback.format_exc())

    # If we didn't get subtitles from recipe, prompt user or fallback to reading srt sidecar
    if raw_srt is None:
        # try .srt next to clip
        srt_try = os.path.splitext(clip_path)[0] + ".srt"
        if os.path.isfile(srt_try):
            print("Found sidecar SRT:", srt_try)
            with open(srt_try, "r", encoding="utf-8") as f:
                raw_srt = f.read()
        else:
            print("No sidecar SRT found and none in recipe; continuing with raw_srt=None (this will likely do nothing).")

    # Show parsed entries
    try:
        entries = l2s_core._prepare_overlay_entries(raw_srt)
        print("Parsed subtitle entries (count={}):".format(len(entries)))
        for i,e in enumerate(entries[:20], start=1):
            print(f" {i}: start={e.get('start')} end={e.get('end')} text={repr(e.get('text')[:80])}")
    except Exception:
        print("Failed to parse subtitles:", traceback.format_exc())

    # Attempt to overlay (capture exceptions)
    try:
        print("Running overlay_on_file(...) — this may call ffmpeg and/or MoviePy; capturing errors...")
        # enable ffmpeg fallback to be verbose by calling overlay_on_file with ffmpeg_crf low quality for speed
        l2s_core.overlay_on_file(clip_path, overlay_instructions=overlay_instructions, srt_stub=raw_srt, main_text=None, prefer_pillow=True, ffmpeg_preset="veryfast", ffmpeg_crf=28)
        print("overlay_on_file completed without raising an exception.")
    except Exception as ex:
        print("overlay_on_file raised an exception:")
        print("TYPE:", type(ex))
        print("EX:", ex)
        # If it's an ffmpeg failure, show more detail if present
        try:
            import traceback as tb
            tb.print_exc()
        except Exception:
            pass

if __name__ == "__main__":
    main()