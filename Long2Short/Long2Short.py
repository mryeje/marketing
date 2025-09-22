#!/usr/bin/env python3
r"""
Long2Short.py - CLI entrypoint for l2s_core.process_recipe

Patches:
- Adds --cleanup-wide-files (already present)
- Adds --overlay-json to allow passing overlay instructions (JSON) that will be
  merged into the recipe before processing (useful when GUI constructs overlay controls
  or when user wants to override recipe overlay fields).
"""
import argparse
import sys
import os
import json
import tempfile
import traceback

def build_parser():
    p = argparse.ArgumentParser(prog="Long2Short", description="Trim/split/stabilize long videos into vertical shorts.")
    p.add_argument("--recipe", required=True, help="Path to recipe JSON")
    p.add_argument("--model", default=None, help="YOLO model path (e.g. yolov8n-pose.pt)")
    p.add_argument("--device", default="auto", help="Device for model ('auto','cpu','cuda')")
    p.add_argument("--apply-stabilize", action="store_true", help="Apply stabilization to trimmed clips")
    p.add_argument("--extract-method", dest="extract_method_hint", choices=["track", "framewise"], help="Extraction method hint")
    p.add_argument("--stabilizer-method", dest="stabilizer_method_hint", choices=["moviepy", "opencv"], help="Stabilizer method hint")
    p.add_argument("--smooth-sigma", type=float, default=None, help="Smoothing sigma for trajectory")
    p.add_argument("--confidence", type=float, default=None, help="Detection confidence threshold (0.0-1.0)")
    p.add_argument("--zoom", type=float, default=None, help="Zoom factor for stabilization")
    p.add_argument("--ybias", type=float, default=None, help="Vertical bias for crop (fraction)")
    p.add_argument("--max-shift-frac", type=float, default=None, help="Max shift fraction")
    p.add_argument("--border-mode", default=None, help="Border mode for transforms (reflect101/reflect/replicate/wrap/constant)")
    p.add_argument("--reattach-audio", action="store_true", help="Reattach audio after OpenCV stabilization")
    p.add_argument("--tmp-dir", default=None, help="Temporary working directory")
    p.add_argument("--target-w", dest="TARGET_W", type=int, default=None, help="Target width for output")
    p.add_argument("--target-h", dest="TARGET_H", type=int, default=None, help="Target height for output")
    p.add_argument("--split-method", dest="split_method_hint", choices=["ffmpeg","moviepy"], help="Split method")
    p.add_argument("--reencode-fallback", action="store_true", help="Allow re-encoding fallback when copy-split fails")
    p.add_argument("--ffmpeg-verbose", action="store_true", help="Show ffmpeg output (verbose)")
    p.add_argument("--cleanup-wide-files", action="store_true", dest="cleanup_wide_files",
                   help="Remove intermediate wide/trimmed files after successful vertical stabilized output")
    p.add_argument("--overlay-json", default=None,
                   help="Path to JSON file with overlay_instructions or clip-level overlay overrides to merge into recipe")
    return p

def _merge_overlays_into_recipe(recipe_path: str, overlay_json_path: str) -> str:
    """
    Load recipe, load overlay JSON, merge overlay fields.
    If overlay_json contains a top-level 'clips' list, merge per-clip by 'id'.
    Otherwise attach as recipe['overlay_instructions'] (global).
    Writes a temp merged recipe JSON and returns its path.
    """
    with open(recipe_path, "r", encoding="utf-8") as f:
        recipe = json.load(f)

    with open(overlay_json_path, "r", encoding="utf-8") as f:
        ov = json.load(f)

    # If overlay JSON appears to contain clips, merge per-id
    if isinstance(ov, dict) and "clips" in ov and isinstance(ov["clips"], list):
        # index overlays by id
        overlay_by_id = {c.get("id"): c for c in ov["clips"] if isinstance(c, dict) and c.get("id")}
        if "clips" in recipe and isinstance(recipe["clips"], list):
            for rc in recipe["clips"]:
                rid = rc.get("id")
                if rid and rid in overlay_by_id:
                    # merge fields (overlay_instructions, text, srt_stub, overlay_text_template, etc.)
                    rc_overlay = overlay_by_id[rid]
                    for k, v in rc_overlay.items():
                        if k == "id":
                            continue
                        rc[k] = v
        # also merge any top-level overlay_instructions if provided
        if "overlay_instructions" in ov:
            recipe["overlay_instructions"] = ov["overlay_instructions"]
    else:
        # treat ov as global overlay_instructions or overrides
        if isinstance(ov, dict):
            # if ov contains overlay_instructions key, use it; otherwise attach ov as overlay_instructions
            if "overlay_instructions" in ov:
                recipe["overlay_instructions"] = ov["overlay_instructions"]
            else:
                # put full object as overlay_instructions
                recipe["overlay_instructions"] = ov

    # write merged recipe to temp file
    fd, tmp_path = tempfile.mkstemp(prefix="l2s_recipe_", suffix=".json")
    os.close(fd)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(recipe, f, indent=2)
    return tmp_path

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)

    # Import l2s_core only when needed; allow helpful error if missing
    try:
        import l2s_core
    except Exception as e:
        print("[ERROR] Failed to import l2s_core:", e, file=sys.stderr)
        traceback.print_exc()
        return 2

    ns = args  # argparse.Namespace

    # If overlay-json provided, merge into recipe and call process_recipe on merged file
    merged_recipe_path = None
    try:
        recipe_path_to_use = ns.recipe
        if ns.overlay_json:
            if not os.path.isfile(ns.overlay_json):
                print(f"[ERROR] overlay-json file not found: {ns.overlay_json}", file=sys.stderr)
                return 2
            merged_recipe_path = _merge_overlays_into_recipe(ns.recipe, ns.overlay_json)
            recipe_path_to_use = merged_recipe_path

        result = l2s_core.process_recipe(recipe_path_to_use, ns)
        print("[INFO] process_recipe finished:", result)
    except Exception as e:
        print("[ERROR] process_recipe raised an exception:", e, file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        # cleanup temp merged recipe if we wrote one
        try:
            if merged_recipe_path and os.path.isfile(merged_recipe_path):
                os.remove(merged_recipe_path)
        except Exception:
            pass

    return 0

if __name__ == "__main__":
    sys.exit(main())