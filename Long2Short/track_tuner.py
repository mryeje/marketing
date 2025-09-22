#!/usr/bin/env python3
r"""
track_tuner.py

Tuner that can either:
 - run its own per-frame YOLO.track -> crop -> write clip flow (internal behavior)
 - OR when --use-repo is set, call l2s_core.extract_targets(...) and l2s_core.stabilize_and_crop(...)

New: when using --use-repo the script will create trimmed "_wide.mp4" pieces (like process_recipe)
prior to extraction by calling l2s_core.trim_and_export_clip(...) when clip entries include start/end
and a source video is available (via --src or queue top-level "src").

Behavior summary:
 - If an entry already references an existing trimmed file (out_path or input file exists), it is used.
 - Else, if entry contains start/end and a source video is available (args.src or recipe has src),
   the script will create a trimmed wide file (named <base>_wide.mp4 in --out-dir) and use that.
 - After the trimmed file exists, the repo extractor (l2s_core.extract_targets) is called and then
   l2s_core.stabilize_and_crop is invoked (if available) to produce the final vertical clip.
 - Falls back to internal per-frame YOLO cropping if l2s_core is not importable or if not using --use-repo.

Usage (repo-backed trimming + repo extractor):
  python track_tuner.py --queue recipe.json --out-dir tuner_out --models yolov8n-pose.pt \
    --confs "0.25" --crop-size 480 --use-repo --src "C:/path/to/source.mp4"

Notes:
 - This script expects either recipe-style entries (with start/end) or entries that already reference
   trimmed files. It tries to be flexible to both formats.
 - If you want the exact same trimming params as process_recipe, you can pass zoom/ybias/etc via CLI
   or rely on l2s_core defaults when the repo's stabilize_and_crop is used.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Try to import ultralytics if present (used when making model objects to pass into l2s_core.extract_targets)
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None  # type: ignore

# Try to import repo functions (optional)
l2s_core = None
try:
    import l2s_core as repo_core  # type: ignore
    l2s_core = repo_core
except Exception:
    l2s_core = None

# ---------------------------
# Helpers for queue parsing
# ---------------------------
def load_queue(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_entries(queue_data: Any) -> List[Dict[str, Any]]:
    if isinstance(queue_data, list):
        return queue_data
    if isinstance(queue_data, dict):
        # recipe format from process_recipe has top-level 'clips'
        if "clips" in queue_data and isinstance(queue_data["clips"], list):
            return queue_data["clips"]
        if "entries" in queue_data and isinstance(queue_data["entries"], list):
            return queue_data["entries"]
        if "queue" in queue_data and isinstance(queue_data["queue"], list):
            return queue_data["queue"]
        return [queue_data]
    return []


def find_input_path(entry: Dict[str, Any], queue_path: Optional[str] = None) -> Optional[str]:
    for key in ("out_path", "source", "in_path", "input", "clip", "path"):
        v = entry.get(key)
        if v:
            # Expand relative paths relative to queue file if provided
            if not os.path.isabs(v) and queue_path:
                cand = os.path.join(os.path.dirname(os.path.abspath(queue_path)), v)
                if os.path.exists(cand):
                    return cand
            return v
    return None


# ---------------------------
# Internal cropping utilities (fallback)
# ---------------------------
def crop_center_on_frame(frame: np.ndarray, center: Tuple[int, int], crop_w: int, crop_h: int) -> np.ndarray:
    h, w = frame.shape[:2]
    cx, cy = center
    half_w = crop_w // 2
    half_h = crop_h // 2
    x0 = max(0, cx - half_w)
    y0 = max(0, cy - half_h)
    x1 = x0 + crop_w
    y1 = y0 + crop_h
    if x1 > w:
        x1 = w
        x0 = max(0, w - crop_w)
    if y1 > h:
        y1 = h
        y0 = max(0, h - crop_h)
    cropped = frame[y0:y1, x0:x1]
    if cropped.shape[0] != crop_h or cropped.shape[1] != crop_w:
        pad_h = crop_h - cropped.shape[0]
        pad_w = crop_w - cropped.shape[1]
        cropped = cv2.copyMakeBorder(cropped, 0, pad_h, 0, pad_w, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    return cropped


def write_video_from_frames(frames_iter, out_path: str, fps: float, crop_w: int, crop_h: int):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_path, fourcc, fps, (crop_w, crop_h))
    if not vw.isOpened():
        raise RuntimeError(f"Failed to open VideoWriter for '{out_path}'")
    for f in frames_iter:
        vw.write(f)
    vw.release()


# ---------------------------
# Internal (original) track & crop flow
# ---------------------------
def process_track_and_make_clip_internal(
    video_path: str,
    model_path: str,
    conf: float,
    crop_w: int,
    crop_h: int,
    out_path: str,
    device: str = "cpu",
    max_frames: Optional[int] = None,
    use_last_fallback: bool = True,
    verbose: bool = False,
) -> Tuple[int, int]:
    if YOLO is None:
        raise RuntimeError("ultralytics.YOLO is not installed or importable. Install with: pip install ultralytics")
    model = YOLO(model_path)
    track_func = getattr(model, "track", None)
    params = dict(source=video_path, conf=conf, device=device, stream=True)
    try:
        if track_func is not None:
            results_iter = track_func(**params)
        else:
            results_iter = model.predict(source=video_path, conf=conf, device=device, stream=True)
    except TypeError:
        if track_func is not None:
            results_iter = track_func(video_path, conf, device)
        else:
            results_iter = model.predict(video_path, conf, device, stream=True)

    frames_out = []
    fps = None
    frames_processed = 0
    last_center = None
    for i, r in enumerate(results_iter):
        if max_frames is not None and frames_processed >= max_frames:
            break
        frame = getattr(r, "orig_img", None) or getattr(r, "orig_img_rgb", None) or getattr(r, "orig_img_bgr", None)
        if frame is None:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                frames_processed += 1
                continue
        if fps is None:
            fps = float(getattr(r, "fps", 0) or 0) or None

        cx = cy = None
        kps = getattr(r, "keypoints", None)
        if kps is not None:
            try:
                arr = np.array(kps)
                if arr.ndim == 3:
                    arr0 = arr[0]
                else:
                    arr0 = arr
                xy = arr0[:, :2]
                valid = ~np.isnan(xy).any(axis=1)
                if np.any(valid):
                    mean_xy = np.mean(xy[valid], axis=0)
                    cx, cy = int(mean_xy[0]), int(mean_xy[1])
            except Exception:
                cx = cy = None
        if cx is None:
            boxes = getattr(r, "boxes", None)
            if boxes is not None:
                xy = getattr(boxes, "xyxy", None)
                if xy is not None:
                    arr = np.array(xy.cpu()) if hasattr(xy, "cpu") else np.array(xy)
                    if arr.shape[0] > 0:
                        sel = 0
                        confs = getattr(boxes, "conf", None)
                        if confs is None:
                            data = getattr(boxes, "data", None)
                            if data is not None:
                                arrd = np.array(data)
                                if arrd.shape[1] >= 5:
                                    confs = arrd[:, 4]
                        if confs is not None:
                            try:
                                confs_arr = np.array(confs)
                                sel = int(np.argmax(confs_arr))
                            except Exception:
                                sel = 0
                        ax1, ay1, ax2, ay2 = arr[sel][:4]
                        cx, cy = int((ax1 + ax2) / 2.0), int((ay1 + ay2) / 2.0)
        if cx is None:
            if use_last_fallback and last_center is not None:
                cx, cy = last_center
            else:
                h, w = frame.shape[:2]
                cx, cy = w // 2, h // 2
        last_center = (cx, cy)
        cropped = crop_center_on_frame(frame, (cx, cy), crop_w, crop_h)
        frames_out.append(cropped)
        frames_processed += 1

    if fps is None:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

    if not frames_out:
        raise RuntimeError("No frames produced by internal track flow")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    write_video_from_frames(frames_out, out_path, float(fps), crop_w, crop_h)
    return len(frames_out), frames_processed


# ---------------------------
# Repo-backed flow: trim -> extract_targets -> stabilize_and_crop
# ---------------------------
def process_track_and_make_clip_repo(
    entry: Dict[str, Any],
    queue_src_video: Optional[str],
    out_dir: str,
    model_path: str,
    conf: float,
    crop_w: int,
    crop_h: int,
    out_path: str,
    device: str = "cpu",
    max_frames: Optional[int] = None,
    use_last_fallback: bool = True,
    verbose: bool = False,
) -> Tuple[int, int]:
    """
    Use l2s_core.trim_and_export_clip (if start/end available) to create a trimmed wide piece,
    then call l2s_core.extract_targets on that trimmed piece and finally l2s_core.stabilize_and_crop
    to produce out_path. Returns (frames_written, frames_processed).
    """
    if l2s_core is None:
        raise RuntimeError("l2s_core not importable in this environment")

    # Determine trimmed source to operate on:
    # 1) If entry references an existing file via out_path/source/in_path, use it.
    inp_path = find_input_path(entry)
    trimmed = None
    if inp_path and os.path.isfile(inp_path):
        trimmed = inp_path
    else:
        # 2) If entry has start/end and we have a source video, trim to a wide file
        start_tc = entry.get("start")
        end_tc = entry.get("end")
        src_video = queue_src_video
        if not src_video:
            # also check top-level 'src' in entry or queue
            src_video = entry.get("src")
        if start_tc is not None and end_tc is not None and src_video and os.path.isfile(src_video):
            # compute trimmed output name inside out_dir
            base = entry.get("id") or entry.get("label") or os.path.splitext(os.path.basename(src_video))[0]
            base_safe = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in str(base)).strip().replace(" ", "_")
            trimmed_name = f"{base_safe}_wide.mp4"
            trimmed = os.path.join(out_dir, trimmed_name)
            # Only trim if not already present
            if not os.path.isfile(trimmed):
                # Convert start/end to seconds using repo helper if available
                try:
                    start_s = l2s_core.timecode_to_seconds(start_tc, video_duration=None)
                except Exception:
                    start_s = None
                try:
                    end_s = l2s_core.timecode_to_seconds(end_tc, video_duration=None)
                except Exception:
                    end_s = None
                # If timecodes are percentage-like or 'middle' etc require duration; attempt to query duration if needed
                if (isinstance(start_s, float) and isinstance(end_s, float)) and start_s is not None and end_s is not None:
                    try:
                        # Call repo trim helper (mirrors process_recipe behavior)
                        if verbose:
                            print(f"[DEBUG] Trimming {src_video} {start_s} -> {end_s} to {trimmed}")
                        # Some signatures accept different params; call with common signature from l2s_core
                        l2s_core.trim_and_export_clip(
                            src_video, float(start_s), float(end_s), trimmed,
                            add_overlay_text=None, overlay_instructions=None,
                            generate_thumbnail=False, thumbnail_time=None, thumbnail_path=None,
                            srt_stub=None, add_text_overlay_flag=False, prefer_pillow=True,
                            write_srt=False
                        )
                    except TypeError:
                        # try a simpler signature if necessary
                        l2s_core.trim_and_export_clip(src_video, float(start_s), float(end_s), trimmed)
                else:
                    raise RuntimeError("Could not parse start/end timecodes for trimming")
        else:
            # 3) no trimmed input and no start/end: try to use any 'out_path' embedded
            maybe = entry.get("out_path") or entry.get("trimmed") or None
            if maybe and os.path.isfile(maybe):
                trimmed = maybe

    if not trimmed or not os.path.isfile(trimmed):
        raise RuntimeError(f"Could not determine or create trimmed input for entry (trimmed={trimmed})")

    # Prepare model object to pass to repo extractor (if ultralytics present).
    model_obj = None
    if YOLO is not None:
        try:
            model_obj = YOLO(model_path)
            try:
                model_obj.to(device)
            except Exception:
                pass
        except Exception as e:
            model_obj = None
            if verbose:
                print(f"[WARN] Failed to load YOLO model for repo extractor: {e}")

    method = "track" if model_obj is not None else "framewise"
    if verbose:
        print(f"[DEBUG] Calling l2s_core.extract_targets(path={trimmed}, method={method}, confidence={conf})")
    xs, ys = l2s_core.extract_targets(trimmed, model=model_obj, smooth_sigma=0.0, method=method, confidence=conf)
    if xs is None or ys is None:
        raise RuntimeError("l2s_core.extract_targets returned no coordinates")

    frames_processed = len(xs)
    valid_count = sum(1 for x, y in zip(xs, ys) if x is not None and y is not None)

    # If stabilize_and_crop present in repo, call it to produce final clip
    stab_fn = getattr(l2s_core, "stabilize_and_crop", None)
    if stab_fn is None:
        # fallback: write simple per-frame cropping using centers (open trimmed and crop)
        cap = cv2.VideoCapture(trimmed)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open trimmed video for fallback writing: {trimmed}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames_out = []
        for i in range(frames_processed):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            cx = xs[i] if xs[i] is not None else (frame.shape[1] // 2)
            cy = ys[i] if ys[i] is not None else (frame.shape[0] // 2)
            cropped = crop_center_on_frame(frame, (int(cx), int(cy)), crop_w, crop_h)
            frames_out.append(cropped)
            if max_frames and len(frames_out) >= max_frames:
                break
        cap.release()
        if not frames_out:
            raise RuntimeError("No frames written in fallback repo flow")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        write_video_from_frames(frames_out, out_path, float(fps), crop_w, crop_h)
        return len(frames_out), frames_processed

    # Call stabilizer from repo
    try:
        kwargs = dict(
            zoom=getattr(l2s_core, "ZOOM", 1.0),
            y_bias=getattr(l2s_core, "Y_BIAS", 0.0),
            max_shift_frac=getattr(l2s_core, "MAX_SHIFT_FRAC", 0.25),
            target_w=crop_w,
            target_h=crop_h,
            border_mode=getattr(l2s_core, "DEFAULT_BORDER_MODE_NAME", "reflect101"),
            method="opencv",
            reattach_audio=True,
            audio_source=trimmed,
        )
        if verbose:
            print(f"[DEBUG] Calling l2s_core.stabilize_and_crop(trimmed={trimmed}, out={out_path}, xs_len={len(xs)})")
        stab_fn(trimmed, out_path, xs, ys, **kwargs)
    except Exception as e:
        raise RuntimeError(f"l2s_core.stabilize_and_crop failed: {e}")

    return valid_count, frames_processed


# ---------------------------
# CLI & main
# ---------------------------
def parse_list_arg(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in str(s).split(",") if p.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tune YOLO tracking + cropping settings against recipe clips.")
    parser.add_argument("--queue", "-q", required=True, help="Path to overlay/clip queue JSON (recipe or queue produced by process_recipe).")
    parser.add_argument("--out-dir", "-o", default="tuner_out", help="Directory to write test clips and map file.")
    parser.add_argument("--models", default="yolov8n-pose.pt", help="Comma-separated model paths or IDs (e.g. yolov8n-pose.pt,yolov8n.pt).")
    parser.add_argument("--confs", default="0.25", help="Comma-separated confidence thresholds (e.g. 0.25,0.2).")
    parser.add_argument("--crop-size", type=int, default=480, help="Square crop size (pixels).")
    parser.add_argument("--crop-w", type=int, default=0, help="Crop width (overrides square crop-size if set).")
    parser.add_argument("--crop-h", type=int, default=0, help="Crop height (overrides square crop-size if set).")
    parser.add_argument("--device", default="cpu", help="Device for ultralytics (cpu or gpu id).")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of queue/clip entries processed (0 = all).")
    parser.add_argument("--max-frames", type=int, default=0, help="Limit frames per clip processed (0 = all frames).")
    parser.add_argument("--map-file", default="tuning_results.csv", help="CSV file mapping output clip -> config.")
    parser.add_argument("--no-last-fallback", action="store_true", help="Do NOT use previous center as fallback when detection missing.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging.")
    parser.add_argument("--use-repo", action="store_true", help="Use repository's l2s_core.extract_targets + stabilize_and_crop when available.")
    parser.add_argument("--src", help="Path to source video (used for trimming when queue entries contain start/end).")
    args = parser.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    models = parse_list_arg(args.models)
    confs = [float(x) for x in parse_list_arg(args.confs)]
    crop_w = args.crop_w if args.crop_w > 0 else args.crop_size
    crop_h = args.crop_h if args.crop_h > 0 else args.crop_size
    queue_data = load_queue(args.queue)
    entries = iter_entries(queue_data)
    if args.limit and args.limit > 0:
        entries = entries[: args.limit]
    # Determine a possible top-level src video from queue file (recipe-style)
    queue_src = None
    if isinstance(queue_data, dict):
        queue_src = queue_data.get("src") or queue_data.get("video") or None
    if args.src:
        queue_src = args.src

    map_lines = []
    line_header = "out_clip,input_or_trimmed,model,conf,crop_w,crop_h,device,frames_written,frames_processed,elapsed_s,used_repo"
    map_lines.append(line_header)

    for e_idx, entry in enumerate(entries):
        # If recipe-style clip (has start/end), we will trim when using repo mode (if source known).
        # If entry already points to an existing input file, use it directly.
        try:
            inp = find_input_path(entry, queue_path=args.queue)
            # Build descriptive base for filenames
            if inp and os.path.isfile(inp):
                base = os.path.splitext(os.path.basename(inp))[0]
            else:
                base = entry.get("id") or entry.get("label") or f"entry{e_idx}"
                base = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in str(base)).strip().replace(" ", "_")

            for m in models:
                for conf in confs:
                    modelname = os.path.splitext(os.path.basename(m))[0].replace("/", "_")
                    outname = f"{base}__track_e{e_idx}__model-{modelname}__conf-{conf:.2f}.mp4"
                    outpath = os.path.join(args.out_dir, outname)
                    print(f"[INFO] Processing entry {e_idx} model={m} conf={conf} -> {outpath}")
                    start = time.time()
                    used_repo = False
                    try:
                        if args.use_repo and l2s_core is not None:
                            # Repo-backed path: will trim if needed then call extract_targets + stabilize_and_crop
                            fw, fp = process_track_and_make_clip_repo(
                                entry=entry,
                                queue_src_video=queue_src,
                                out_dir=args.out_dir,
                                model_path=m,
                                conf=conf,
                                crop_w=crop_w,
                                crop_h=crop_h,
                                out_path=outpath,
                                device=args.device,
                                max_frames=(args.max_frames if args.max_frames > 0 else None),
                                use_last_fallback=(not args.no_last_fallback),
                                verbose=args.verbose,
                            )
                            used_repo = True
                        else:
                            # Internal per-frame flow expects an input path; if entry doesn't point to a file, skip
                            if not inp or not os.path.isfile(inp):
                                print(f"[WARNING] Entry {e_idx} has no input file to run internal flow: {inp} -- skipping")
                                map_lines.append(",".join([outpath, str(inp or ""), m, f"{conf:.3f}", str(crop_w), str(crop_h), str(args.device), "0", "0", "0.00", "False"]))
                                continue
                            fw, fp = process_track_and_make_clip_internal(
                                video_path=inp,
                                model_path=m,
                                conf=conf,
                                crop_w=crop_w,
                                crop_h=crop_h,
                                out_path=outpath,
                                device=args.device,
                                max_frames=(args.max_frames if args.max_frames > 0 else None),
                                use_last_fallback=(not args.no_last_fallback),
                                verbose=args.verbose,
                            )
                        elapsed = time.time() - start
                        map_lines.append(",".join([outpath, str(inp or ""), m, f"{conf:.3f}", str(crop_w), str(crop_h), str(args.device), str(fw), str(fp), f"{elapsed:.2f}", str(used_repo)]))
                    except Exception as ex:
                        elapsed = time.time() - start
                        print(f"[ERROR] Failed processing entry {e_idx} {inp} model={m} conf={conf}: {ex}")
                        if args.verbose:
                            import traceback
                            traceback.print_exc()
                        map_lines.append(",".join([outpath, str(inp or ""), m, f"{conf:.3f}", str(crop_w), str(crop_h), str(args.device), "0", "0", f"{elapsed:.2f}", str(used_repo)]))
                        continue
        except Exception as ex_outer:
            print(f"[ERROR] Unexpected error processing entry {e_idx}: {ex_outer}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            continue

    map_path = os.path.join(args.out_dir, args.map_file)
    with open(map_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(map_lines))
    print(f"[INFO] Tuning complete. Map file: {map_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())