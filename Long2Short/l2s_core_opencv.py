"""
l2s_core_opencv.py

Fast OpenCV + ffmpeg helpers adapted into l2s_core style:

- extract_targets_framewise(video_path, model=None, model_path=None, device='auto', smooth_sigma=5, keypoint_indices=(0,9,10))
    Accepts either a loaded ultralytics.YOLO model instance or a model_path string.
    Returns (xs, ys) arrays aligned to frames read by cv2.VideoCapture, with NaNs interpolated and Gaussian smoothed.

- stabilize_and_crop_opencv(video_in, video_out, xs, ys, zoom=1.05, y_bias=0.0, max_shift_frac=0.25,
                            target_w=1080, target_h=1920, border_mode='reflect101',
                            reencode_codec='libx264', reattach_audio=False, audio_source=None, tmp_dir=None)
    Fast per-frame warp + crop using OpenCV. Writes a temporary video (no audio) then optionally reattaches audio with ffmpeg.

- reattach_audio_ffmpeg(video_noaudio, source_with_audio, out_path, audio_codec='aac')
    Uses ffmpeg to copy video stream and re-attach audio.

- split_into_equal_shorts_ffmpeg(video_in, template_out, n=3, reencode=False)
    Splits into N equal segments using ffmpeg; by default does stream-copy (-c copy).

- trim_clip_ffmpeg(video_in, start_s, end_s, out_path, reencode=False)
    Extracts a single clip between start and end; stream-copy preferred.

Notes:
- These helpers prefer ffmpeg to be on PATH.
- They expose parameters (zoom, smooth_sigma, border mode, codecs).
- They are designed to plug into existing l2s_core workflows; they intentionally accept model instances
  so the caller (GUI/CLI) can load a model once and reuse it.

Usage examples:
    from l2s_core_opencv import extract_targets_framewise, stabilize_and_crop_opencv
    xs, ys = extract_targets_framewise("input.mp4", model=loaded_yolo, smooth_sigma=6)
    stabilize_and_crop_opencv("input.mp4", "stabilized_no_audio.mp4", xs, ys, reattach_audio=True, audio_source="input.mp4")

"""

from typing import Optional, Sequence, Tuple, List
import os
import tempfile
import subprocess
import math
import numpy as np
import cv2

# gaussian smoother
from scipy.ndimage import gaussian_filter1d

# Try to import ultralytics.YOLO lazily inside functions when needed.
YOLO_AVAILABLE = True
try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO_AVAILABLE = False

# Default target vertical short resolution
DEFAULT_TARGET_W = 1080
DEFAULT_TARGET_H = 1920


def _border_mode_to_cv(border_name: str):
    n = (border_name or "").lower()
    if n in ("reflect101", "reflect_101"):
        return cv2.BORDER_REFLECT_101
    if n == "reflect":
        return cv2.BORDER_REFLECT
    if n in ("replicate", "repeat"):
        return cv2.BORDER_REPLICATE
    if n == "wrap":
        return cv2.BORDER_WRAP
    if n in ("constant", "black"):
        return cv2.BORDER_CONSTANT
    return cv2.BORDER_REFLECT_101


def extract_targets_framewise(video_path: str,
                              model=None,
                              model_path: Optional[str] = None,
                              device: str = "auto",
                              smooth_sigma: float = 5.0,
                              keypoint_indices: Tuple[int, int, int] = (0, 9, 10),
                              verbose: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """
    Framewise target extraction (face + hands mean) using ultralytics YOLO per-frame inference.

    Parameters:
    - video_path: input path
    - model: optional loaded ultralytics.YOLO instance; if provided, `model_path` is ignored.
    - model_path: if `model` is None, attempt to load YOLO(model_path) (requires ultralytics installed).
    - device: forwarded device string when loading model (if using model_path).
    - smooth_sigma: gaussian filter sigma to smooth output tracks.
    - keypoint_indices: (face_index, left_wrist_index, right_wrist_index) into keypoints array.
    - verbose: print progress/info.

    Returns:
    - xs, ys: numpy arrays of float (length = number of frames read). Missing values are interpolated and smoothed.
    """
    if verbose:
        print(f"[INFO] extract_targets_framewise: opening video: {video_path}")
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    # ensure a model is available
    loaded_model = None
    if model is not None:
        loaded_model = model
    else:
        if model_path is None:
            raise ValueError("Either model or model_path must be provided")
        if not YOLO_AVAILABLE:
            raise RuntimeError("ultralytics.YOLO is not available (install ultralytics)")
        if verbose:
            print(f"[INFO] Loading YOLO model from: {model_path}")
        loaded_model = YOLO(model_path)
        try:
            # try moving to device if possible
            if device and device != "auto":
                loaded_model.to(device)
        except Exception:
            # ignore if model has no .to or fails
            pass

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    xs: List[Optional[float]] = []
    ys: List[Optional[float]] = []
    frame_idx = 0

    # While-loop reading frames
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        cx = None
        cy = None

        try:
            # ultralytics model inference: prefer calling the model directly on numpy image.
            # Some YOLO versions accept model(frame) or model.predict; attempt both patterns.
            results = None
            try:
                results = loaded_model(frame)  # type: ignore
            except Exception:
                try:
                    results = loaded_model.predict(frame)  # type: ignore
                except Exception:
                    results = None

            if results is not None and len(results) > 0:
                # results[0] may have .keypoints or .keypoints.xy depending on API
                r0 = results[0]
                kps = None
                # ultralytics Results may have .keypoints or .masks etc; try common accesses
                try:
                    if hasattr(r0, "keypoints") and r0.keypoints is not None:
                        # r0.keypoints.xy maybe a tensor
                        try:
                            kps_arr = r0.keypoints.xy.cpu().numpy()
                        except Exception:
                            try:
                                kps_arr = np.array(r0.keypoints.xy)
                            except Exception:
                                kps_arr = None
                        kps = kps_arr
                    elif hasattr(r0, "keypoints") and isinstance(r0.keypoints, (list, tuple, np.ndarray)):
                        kps = np.array(r0.keypoints)
                    # older API: r0.keypoints maybe directly numpy
                except Exception:
                    kps = None

                if kps is not None and kps.size != 0:
                    # kps shape expected (N_people, N_keypoints, 2)
                    if kps.ndim == 3 and kps.shape[0] > 0:
                        person = kps[0]
                        pts = []
                        for idx in keypoint_indices:
                            if idx < person.shape[0]:
                                pt = person[idx]
                                if len(pt) >= 2:
                                    px, py = float(pt[0]), float(pt[1])
                                    if not math.isnan(px) and not math.isnan(py):
                                        pts.append((px, py))
                        if pts:
                            arr = np.array(pts, float)
                            cx, cy = float(arr[:, 0].mean()), float(arr[:, 1].mean())
        except Exception as e:
            if verbose:
                print(f"[WARN] frame {frame_idx}: inference error: {e}")

        xs.append(cx)
        ys.append(cy)
        frame_idx += 1

    cap.release()

    # convert to numpy and interpolate missing values
    idx = np.arange(len(xs))
    xs_a = np.array([np.nan if v is None else v for v in xs], dtype=float)
    ys_a = np.array([np.nan if v is None else v for v in ys], dtype=float)

    if np.any(~np.isnan(xs_a)):
        xs_interp = np.interp(idx, idx[~np.isnan(xs_a)], xs_a[~np.isnan(xs_a)])
    else:
        xs_interp = np.zeros_like(xs_a)
    if np.any(~np.isnan(ys_a)):
        ys_interp = np.interp(idx, idx[~np.isnan(ys_a)], ys_a[~np.isnan(ys_a)])
    else:
        ys_interp = np.zeros_like(ys_a)

    # smooth
    if smooth_sigma and smooth_sigma > 0:
        xs_s = gaussian_filter1d(xs_interp, sigma=smooth_sigma, mode="nearest")
        ys_s = gaussian_filter1d(ys_interp, sigma=smooth_sigma, mode="nearest")
    else:
        xs_s, ys_s = xs_interp, ys_interp

    if verbose:
        print(f"[INFO] extract_targets_framewise: frames={len(xs_s)}, smoothed sigma={smooth_sigma}")

    return xs_s, ys_s


def stabilize_and_crop_opencv(video_in: str,
                              video_out: str,
                              xs: np.ndarray,
                              ys: np.ndarray,
                              zoom: float = 1.05,
                              y_bias: float = 0.0,
                              max_shift_frac: float = 0.25,
                              target_w: int = DEFAULT_TARGET_W,
                              target_h: int = DEFAULT_TARGET_H,
                              border_mode: str = "reflect101",
                              reencode_codec: str = "libx264",
                              reattach_audio: bool = False,
                              audio_source: Optional[str] = None,
                              tmp_dir: Optional[str] = None,
                              verbose: bool = True) -> str:
    """
    Fast OpenCV stabilization + crop pipeline.

    Writes a temporary video file without audio, then optionally reattaches audio with ffmpeg.

    Returns:
        final output path (video_out if audio handling succeeded).
    """
    if verbose:
        print(f"[INFO] stabilize_and_crop_opencv: input={video_in}, output={video_out}")
    if not os.path.isfile(video_in):
        raise FileNotFoundError(f"video_in not found: {video_in}")

    tmp_dir = tmp_dir or tempfile.gettempdir()
    base_tmp = os.path.join(tmp_dir, f"l2s_stab_{os.getpid()}_{int(math.floor(tempfile.mkstemp()[1][-6:]) if False else 0)}")
    # safer: create a temp filename
    tmp_video_noaudio = os.path.join(tmp_dir, next(tempfile._get_candidate_names()) + "_stab_noaudio.mp4")

    cap = cv2.VideoCapture(video_in)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open input video: {video_in}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or math.isnan(fps):
        fps = 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0 else len(xs)

    if verbose:
        print(f"[INFO] input size: {w}x{h}@{fps}fps, frames (cap)={total_frames}, xs_len={len(xs)}")

    # compute target center in source coordinates
    cx_target = w / 2.0
    cy_target = h / 2.0 + y_bias * h

    # ensure xs/ys lengths match at least available frames (pad or trim)
    nframes = total_frames
    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)
    if len(xs_arr) < nframes:
        pad_len = nframes - len(xs_arr)
        xs_arr = np.pad(xs_arr, (0, pad_len), mode="edge")
        ys_arr = np.pad(ys_arr, (0, pad_len), mode="edge")
    elif len(xs_arr) > nframes:
        xs_arr = xs_arr[:nframes]
        ys_arr = ys_arr[:nframes]

    # compute shifts needed (target - measured)
    x_s = (xs_arr - (w / 2.0)) * zoom + (w / 2.0)
    y_s = (ys_arr - (h / 2.0)) * zoom + (h / 2.0)
    tx_arr = cx_target - x_s
    ty_arr = cy_target - y_s

    max_shift = max_shift_frac * min(w, h)
    bmode_cv = _border_mode_to_cv(border_mode)

    # Choose codec / fourcc for VideoWriter - prefer writing raw frames and then re-encoding via ffmpeg for best compatibility
    # Use mp4v or avc1; on many systems libx264 via ffmpeg will be used in the re-encode step. For cross-platform try mp4v.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_writer = cv2.VideoWriter(tmp_video_noaudio, fourcc, fps, (target_w, target_h))

    frame_idx = 0
    written = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx >= len(tx_arr):
            # no more track data
            break

        tx = float(np.clip(-tx_arr[frame_idx], -max_shift, max_shift))
        ty = float(np.clip(-ty_arr[frame_idx], -max_shift, max_shift))

        # apply zoom scaling about center
        M_scale = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0, zoom)
        frame_scaled = cv2.warpAffine(frame, M_scale, (w, h), borderMode=bmode_cv)

        # apply translation
        M_trans = np.float32([[1, 0, tx], [0, 1, ty]])
        frame_trans = cv2.warpAffine(frame_scaled, M_trans, (w, h), borderMode=bmode_cv)

        # crop to target aspect 9:16 or target_w/target_h
        target_aspect = float(target_w) / float(target_h)
        in_aspect = float(w) / float(h)
        if in_aspect > target_aspect:
            new_w = int(h * target_aspect)
            x1 = w // 2 - new_w // 2
            x2 = x1 + new_w
            frame_crop = frame_trans[:, x1:x2]
        else:
            new_h = int(w / target_aspect)
            y1 = h // 2 - new_h // 2
            y2 = y1 + new_h
            frame_crop = frame_trans[y1:y2, :]

        # final resize
        frame_out = cv2.resize(frame_crop, (target_w, target_h))
        out_writer.write(frame_out.astype('uint8'))
        written += 1
        frame_idx += 1

    cap.release()
    out_writer.release()

    if verbose:
        print(f"[INFO] stabilize_and_crop_opencv: wrote {written} frames to temporary (no audio): {tmp_video_noaudio}")

    final_out = video_out
    # If user requested audio reattachment, ensure audio_source is provided or fallback to original input
    if reattach_audio:
        audio_src = audio_source or video_in
        try:
            reattach_audio_ffmpeg(tmp_video_noaudio, audio_src, video_out)
            final_out = video_out
            if verbose:
                print(f"[INFO] Audio reattached to produce: {final_out}")
            # remove the temporary file
            try:
                os.remove(tmp_video_noaudio)
            except Exception:
                pass
        except Exception as e:
            # if reattach fails, keep the no-audio file and raise
            print(f"[ERROR] audio reattach failed: {e}. temporary file left at: {tmp_video_noaudio}")
            raise
    else:
        # move/rename tmp_video_noaudio -> video_out (overwrite)
        try:
            os.replace(tmp_video_noaudio, video_out)
            final_out = video_out
        except Exception:
            # fallback to copy
            import shutil
            shutil.copy(tmp_video_noaudio, video_out)
            final_out = video_out

    return final_out


def reattach_audio_ffmpeg(video_noaudio: str, source_with_audio: str, out_path: str, audio_codec: str = "aac"):
    """
    Use ffmpeg to copy the video stream from 'video_noaudio' and the audio stream from 'source_with_audio'
    into out_path. Requires ffmpeg on PATH.

    Command:
      ffmpeg -y -i video_noaudio -i source_with_audio -c:v copy -c:a <audio_codec> -map 0:v:0 -map 1:a:0 out_path
    """
    if not os.path.isfile(video_noaudio):
        raise FileNotFoundError(f"video_noaudio not found: {video_noaudio}")
    if not os.path.isfile(source_with_audio):
        raise FileNotFoundError(f"source_with_audio not found: {source_with_audio}")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_noaudio,
        "-i", source_with_audio,
        "-c:v", "copy",
        "-c:a", audio_codec,
        "-map", "0:v:0",
        "-map", "1:a:0",
        out_path
    ]
    # run and capture output for debugging
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        # include stderr for troubleshooting
        raise RuntimeError(f"ffmpeg audio reattach failed: returncode={proc.returncode}\nstderr:\n{proc.stderr}")
    return out_path


def split_into_equal_shorts_ffmpeg(video_in: str, template_out: str, n: int = 3, reencode: bool = False, verbose: bool = True) -> List[str]:
    """
    Split video_in into n equal-duration segments using ffmpeg.
    template_out should be a format string with one integer placeholder, e.g. "short_part{}.mp4".
    If reencode is False, uses stream-copy "-c copy" (fast). If it fails (keyframe issues), consider reencode=True.
    """
    if verbose:
        print(f"[INFO] split_into_equal_shorts_ffmpeg: video_in={video_in}, n={n}")

    if not os.path.isfile(video_in):
        raise FileNotFoundError(f"video_in not found: {video_in}")

    # get duration via ffprobe (preferred) or fallback to cv2
    dur = None
    try:
        # ffprobe approach
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_in]
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if out.returncode == 0:
            dur = float(out.stdout.strip())
    except Exception:
        dur = None

    if dur is None:
        # fallback to cv2
        cap = cv2.VideoCapture(video_in)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if frames and fps:
                dur = float(frames) / float(fps)
            cap.release()
    if dur is None:
        raise RuntimeError("Could not determine input duration for splitting")

    seg_dur = dur / float(n)
    outs = []
    for i in range(n):
        start = i * seg_dur
        out = template_out.format(i + 1)
        if reencode:
            cmd = [
                "ffmpeg", "-y", "-i", video_in,
                "-ss", str(start),
                "-t", str(seg_dur),
                "-c:v", "libx264", "-c:a", "aac",
                out
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", video_in,
                "-ss", str(start),
                "-t", str(seg_dur),
                "-c", "copy",
                out
            ]
        if verbose:
            print(f"[INFO] ffmpeg splitting -> {out}")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            # try reencoding fallback if copy failed
            if not reencode:
                if verbose:
                    print(f"[WARN] ffmpeg copy split failed for segment {i+1}, retrying with re-encode")
                cmd = [
                    "ffmpeg", "-y", "-i", video_in,
                    "-ss", str(start),
                    "-t", str(seg_dur),
                    "-c:v", "libx264", "-c:a", "aac",
                    out
                ]
                proc2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc2.returncode != 0:
                    raise RuntimeError(f"ffmpeg split failed for segment {i+1}: {proc2.stderr}")
            else:
                raise RuntimeError(f"ffmpeg split failed for segment {i+1}: {proc.stderr}")
        outs.append(out)
    return outs


def trim_clip_ffmpeg(video_in: str, start_s: float, end_s: float, out_path: str, reencode: bool = False, verbose: bool = True) -> str:
    """
    Trim video_in between start_s and end_s and write out_path.
    - reencode=False will attempt "-c copy" (very fast, but may require keyframe alignment).
    - reencode=True will re-encode using libx264/aac.
    """
    if verbose:
        print(f"[INFO] trim_clip_ffmpeg: {video_in} {start_s}->{end_s} -> {out_path}")
    if not os.path.isfile(video_in):
        raise FileNotFoundError(f"video_in not found: {video_in}")

    duration = max(0.0, float(end_s) - float(start_s))
    if reencode:
        cmd = [
            "ffmpeg", "-y", "-i", video_in,
            "-ss", str(start_s),
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac",
            out_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", video_in,
            "-ss", str(start_s),
            "-t", str(duration),
            "-c", "copy",
            out_path
        ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        if not reencode:
            # try reencode fallback
            if verbose:
                print("[WARN] trim with copy failed, retrying with re-encode")
            cmd2 = [
                "ffmpeg", "-y", "-i", video_in,
                "-ss", str(start_s),
                "-t", str(duration),
                "-c:v", "libx264", "-c:a", "aac",
                out_path
            ]
            proc2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc2.returncode != 0:
                raise RuntimeError(f"ffmpeg trim failed: {proc2.stderr}")
            return out_path
        raise RuntimeError(f"ffmpeg trim failed: {proc.stderr}")
    return out_path