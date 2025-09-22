#!/usr/bin/env python3
r"""
grid_runner.py

Grid-runner that calls the repository-backed extractor+stabilizer (l2s_core) across a parameter grid.

What it does
- Reads a recipe/queue JSON (recipe style with "clips" or a list of entries).
- Builds the cross product of provided parameter lists:
    smooth_sigma, detection confidence, zoom, y_bias, max_shift_frac, models
- For every combo and every recipe clip (or a limited number via --limit):
    - Trim the source to a _wide.mp4 using l2s_core.trim_and_export_clip (if clip has start/end)
      OR use an existing referenced input file in the recipe entry.
    - Call l2s_core.extract_targets(trimmed, model=model_obj, smooth_sigma=smooth_sigma, confidence=conf)
    - Call l2s_core.stabilize_and_crop(trimmed, out_path, xs, ys,
          zoom=zoom, y_bias=y_bias, max_shift_frac=max_shift_frac, target_w=..., target_h=...)
- Writes a CSV map file with one row per test that includes all tested parameters and runtime stats.

Notes / requirements
- This script expects l2s_core to be importable from the same repository (Long2Short).
- If you want to use GPU for detection, install ultralytics and a CUDA-capable torch, and pass --device "0" or "cuda:0".
- The grid size is the product of list lengths; be careful (combinatorial explosion).
"""
from __future__ import annotations
import argparse
import csv
import itertools
import json
import math
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Optional ultralytics model wrapper
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None  # type: ignore

# repo functions (must be importable)
try:
    import l2s_core as repo_core  # type: ignore
except Exception:
    repo_core = None  # type: ignore

# -------------------------
# Helpers
# -------------------------
def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def iter_recipe_clips(queue_data: Any) -> List[Dict[str, Any]]:
    if isinstance(queue_data, dict):
        if "clips" in queue_data and isinstance(queue_data["clips"], list):
            return queue_data["clips"]
        if "entries" in queue_data and isinstance(queue_data["entries"], list):
            return queue_data["entries"]
        return [queue_data]
    if isinstance(queue_data, list):
        return queue_data
    return []

def find_input_path(entry: Dict[str, Any], queue_path: Optional[str] = None) -> Optional[str]:
    for key in ("out_path", "source", "in_path", "input", "clip", "path"):
        v = entry.get(key)
        if v:
            if not os.path.isabs(v) and queue_path:
                cand = os.path.join(os.path.dirname(os.path.abspath(queue_path)), v)
                if os.path.exists(cand):
                    return cand
            return v
    return None

def ensure_dir(path: str):
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def timecode_to_seconds_safe(tc: Optional[str], dur: Optional[float] = None) -> Optional[float]:
    if tc is None:
        return None
    try:
        # prefer repo helper if available
        if repo_core is not None and hasattr(repo_core, "timecode_to_seconds"):
            return repo_core.timecode_to_seconds(tc, dur)
    except Exception:
        pass
    # fallback simple parser HH:MM:SS[.ms] or MM:SS or seconds
    s = str(tc).replace(",", ".").strip()
    parts = s.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60.0 + float(parts[1])
        if len(parts) >= 3:
            h = int(parts[-3]); m = int(parts[-2]); sec = float(parts[-1])
            return h*3600 + m*60 + sec
    except Exception:
        return None
    return None

# -------------------------
# Core per-test execution
# -------------------------
def make_model_object(model_path: str, device: str) -> Optional[Any]:
    if YOLO is None:
        return None
    try:
        m = YOLO(model_path)
        try:
            m.to(device)
        except Exception:
            pass
        return m
    except Exception:
        return None

def run_test_on_entry(entry: Dict[str, Any], queue_src: Optional[str], out_dir: str, crop_size: int,
                      model_path: str, device: str, conf: float, smooth_sigma: float,
                      zoom: float, y_bias: float, max_shift_frac: float,
                      max_frames: Optional[int], verbose: bool) -> Tuple[str, str, int, int, float, bool]:
    """
    Returns: (out_path, trimmed_path, frames_written, frames_processed, elapsed_s, used_repo)
    """
    start_t = time.time()
    used_repo = False
    # determine base name
    base = entry.get("id") or entry.get("label") or f"entry"
    base_safe = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in str(base)).strip().replace(" ", "_")
    modelname = os.path.splitext(os.path.basename(model_path))[0].replace("/", "_")
    out_name = f"{base_safe}__model-{modelname}__conf-{conf:.3f}__ss-{smooth_sigma:.2f}__zoom-{zoom:.2f}__yb-{y_bias:.2f}__msf-{max_shift_frac:.2f}.mp4"
    out_path = os.path.join(out_dir, out_name)
    trimmed = None

    # find input or trim
    inp_ref = find_input_path(entry)
    if inp_ref and os.path.isfile(inp_ref):
        trimmed = inp_ref
    else:
        if repo_core is None:
            raise RuntimeError("l2s_core not importable; cannot trim clip automatically")
        start_tc = entry.get("start")
        end_tc = entry.get("end")
        src_video = queue_src or entry.get("src")
        if not src_video or not os.path.isfile(src_video):
            raise RuntimeError("No source video available to trim for this entry")
        trimmed_name = f"{base_safe}_wide.mp4"
        trimmed = os.path.join(out_dir, trimmed_name)
        if not os.path.isfile(trimmed):
            start_s = timecode_to_seconds_safe(start_tc)
            end_s = timecode_to_seconds_safe(end_tc)
            if start_s is None or end_s is None:
                raise RuntimeError(f"Could not parse start/end times: start={start_tc} end={end_tc}")
            if verbose:
                print(f"[DEBUG] Trimming {src_video} {start_s}->{end_s} -> {trimmed}")
            # call repo trim helper
            repo_core.trim_and_export_clip(src_video, float(start_s), float(end_s), trimmed,
                                           add_overlay_text=None, overlay_instructions=None,
                                           generate_thumbnail=False, thumbnail_time=None, thumbnail_path=None,
                                           srt_stub=None, add_text_overlay_flag=False, prefer_pillow=True,
                                           write_srt=False)

    # extraction and stabilization
    if repo_core is None:
        raise RuntimeError("l2s_core not importable; cannot run extractor/stabilizer")

    # build model object if ultralytics present
    model_obj = make_model_object(model_path, device)

    if verbose:
        print(f"[DEBUG] extract_targets(trimmed={trimmed}, conf={conf}, smooth_sigma={smooth_sigma})")
    xs, ys = repo_core.extract_targets(trimmed, model=model_obj, smooth_sigma=smooth_sigma, method="track" if model_obj else "framewise", confidence=conf)
    if xs is None or ys is None:
        raise RuntimeError("extract_targets returned empty centers")

    frames_processed = len(xs)
    valid_count = sum(1 for x in xs if x is not None)

    # call stabilize_and_crop if available
    stab_fn = getattr(repo_core, "stabilize_and_crop", None)
    if stab_fn is None:
        # fallback: try to write per-frame crop as a simple fallback (not expected for repo)
        raise RuntimeError("repo_core.stabilize_and_crop not found; grid runner expects repo-backed stabilizer")
    kwargs = dict(
        zoom=zoom,
        y_bias=y_bias,
        max_shift_frac=max_shift_frac,
        target_w=crop_size,
        target_h=crop_size,
        border_mode=getattr(repo_core, "DEFAULT_BORDER_MODE_NAME", "reflect101"),
        method="opencv",
        reattach_audio=True,
        audio_source=trimmed,
    )
    if verbose:
        print(f"[DEBUG] stabilize_and_crop -> {out_path} kwargs={kwargs}")
    stab_fn(trimmed, out_path, xs, ys, **kwargs)
    elapsed = time.time() - start_t
    return out_path, trimmed, valid_count, frames_processed, elapsed, True

# -------------------------
# CSV write helpers
# -------------------------
def append_csv_row(csv_path: str, row: Dict[str, Any], header: List[str]):
    exists = os.path.isfile(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        if not exists:
            writer.writeheader()
        writer.writerow(row)

# -------------------------
# CLI / main
# -------------------------
def parse_list_arg(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in str(s).split(",") if p.strip()]

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a grid of extractor/stabilizer tests using l2s_core")
    parser.add_argument("--queue", "-q", required=True, help="Recipe/queue JSON (recipe or list of entries).")
    parser.add_argument("--out-dir", "-o", required=True, help="Directory for outputs and map CSV.")
    parser.add_argument("--models", default="yolov8n.pt", help="Comma-separated model paths/ids.")
    parser.add_argument("--confs", default="0.25", help="Comma-separated detection confidences.")
    parser.add_argument("--smooth-sigmas", default="0.0", help="Comma-separated smoothing sigma values (float).")
    parser.add_argument("--zooms", default="1.0", help="Comma-separated zoom values.")
    parser.add_argument("--y-biases", default="0.0", help="Comma-separated vertical bias values.")
    parser.add_argument("--max-shifts", default="0.25", help="Comma-separated max_shift_frac values.")
    parser.add_argument("--crop-size", type=int, default=480, help="Square target crop size (px).")
    parser.add_argument("--device", default="cpu", help="Device for models (cpu, 0, cuda:0, etc.).")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of recipe clips processed (0 = all).")
    parser.add_argument("--max-frames", type=int, default=0, help="Limit frames per clip (0 = all).")
    parser.add_argument("--map-file", default="grid_tuning_results.csv", help="Output CSV map filename (written into --out-dir).")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    ensure_dir(args.out_dir)
    models = parse_list_arg(args.models)
    confs = [float(x) for x in parse_list_arg(args.confs)]
    smooth_sigmas = [float(x) for x in parse_list_arg(args.smooth_sigmas)]
    zooms = [float(x) for x in parse_list_arg(args.zooms)]
    y_biases = [float(x) for x in parse_list_arg(args.y_biases)]
    max_shifts = [float(x) for x in parse_list_arg(args.max_shifts)]

    queue_data = load_json(args.queue)
    clips = iter_recipe_clips(queue_data)
    if args.limit and args.limit > 0:
        clips = clips[: args.limit]
    queue_src = None
    if isinstance(queue_data, dict):
        queue_src = queue_data.get("src") or queue_data.get("video") or None

    combos = list(itertools.product(models, confs, smooth_sigmas, zooms, y_biases, max_shifts))
    total_runs = len(clips) * len(combos)
    print(f"[INFO] Running grid: clips={len(clips)} combos={len(combos)} total_runs={total_runs}")
    if total_runs == 0:
        print("[ERROR] No runs to perform (check args).")
        return 2

    map_csv = os.path.join(args.out_dir, args.map_file)
    header = ["out_clip", "input_trimmed", "model", "conf", "smooth_sigma", "zoom", "y_bias", "max_shift_frac", "frames_written", "frames_processed", "elapsed_s", "used_repo", "error"]

    # iterate
    for c_idx, clip in enumerate(clips):
        for combo in combos:
            model_path, conf, smooth_sigma, zoom, y_bias, max_shift_frac = combo
            try:
                print(f"[INFO] Clip {c_idx+1}/{len(clips)} - model={model_path} conf={conf} ss={smooth_sigma} zoom={zoom} ybias={y_bias} msf={max_shift_frac}")
                out_path, trimmed, fw, fp, elapsed, used_repo = run_test_on_entry(
                    entry=clip,
                    queue_src=queue_src,
                    out_dir=args.out_dir,
                    crop_size=args.crop_size,
                    model_path=model_path,
                    device=args.device,
                    conf=conf,
                    smooth_sigma=smooth_sigma,
                    zoom=zoom,
                    y_bias=y_bias,
                    max_shift_frac=max_shift_frac,
                    max_frames=(args.max_frames if args.max_frames > 0 else None),
                    verbose=args.verbose
                )
                row = {
                    "out_clip": out_path,
                    "input_trimmed": trimmed,
                    "model": model_path,
                    "conf": f"{conf:.3f}",
                    "smooth_sigma": f"{smooth_sigma:.3f}",
                    "zoom": f"{zoom:.3f}",
                    "y_bias": f"{y_bias:.3f}",
                    "max_shift_frac": f"{max_shift_frac:.3f}",
                    "frames_written": fw,
                    "frames_processed": fp,
                    "elapsed_s": f"{elapsed:.2f}",
                    "used_repo": used_repo,
                    "error": ""
                }
                append_csv_row(map_csv, row, header)
            except Exception as ex:
                print(f"[ERROR] Test failed for combo {combo} on clip {c_idx}: {ex}")
                if args.verbose:
                    import traceback; traceback.print_exc()
                err_row = {
                    "out_clip": "",
                    "input_trimmed": find_input_path(clip) or "",
                    "model": combo[0] if combo else "",
                    "conf": f"{combo[1]:.3f}" if len(combo) > 1 else "",
                    "smooth_sigma": f"{combo[2]:.3f}" if len(combo) > 2 else "",
                    "zoom": f"{combo[3]:.3f}" if len(combo) > 3 else "",
                    "y_bias": f"{combo[4]:.3f}" if len(combo) > 4 else "",
                    "max_shift_frac": f"{combo[5]:.3f}" if len(combo) > 5 else "",
                    "frames_written": 0,
                    "frames_processed": 0,
                    "elapsed_s": 0.0,
                    "used_repo": False,
                    "error": str(ex)
                }
                append_csv_row(map_csv, err_row, header)
                continue

    print(f"[INFO] Grid complete. Map file: {map_csv}")
    return 0

if __name__ == "__main__":
    sys.exit(main())