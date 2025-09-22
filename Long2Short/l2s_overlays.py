#!/usr/bin/env python3
"""
l2s_overlays.py

Standalone overlay/subtitle post-processor for Long2Short pipeline.

- Reads an overlays_queue_*.json file produced by l2s_core.process_recipe
  (or builds a queue from a recipe + outdir).
- Applies per-frame overlays and subtitles to finished vertical clips.
- Primary renderer uses Pillow (per-frame drawing via MoviePy frame lambda).
  Falls back to MoviePy TextClip-based overlays if Pillow is not available.
- Writes an updated clip in-place (writes to a temp file then replaces original).

Usage:
  python l2s_overlays.py --queue /path/to/overlays_queue_xxx.json
  python l2s_overlays.py --recipe /path/to/recipe.json --outdir /path/to/output_dir

Options:
  --dry-run       : do not write changes, only report actions
  --parallel N    : process up to N clips in parallel (uses multiprocessing)
  --keep-temp     : keep temp output files on failure for debugging
"""
from typing import Optional, Any, List, Dict, Tuple
import os
import re
import json
import datetime
import argparse
import tempfile
import shutil
import math
import multiprocessing
import traceback

# Try to import Pillow and MoviePy; fallbacks handled
try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor
    PIL_AVAILABLE = True
except Exception:
    Image = ImageDraw = ImageFont = ImageColor = None
    PIL_AVAILABLE = False

try:
    import numpy as np
except Exception:
    np = None

try:
    import moviepy
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
    MOVIEPY_AVAILABLE = True
except Exception:
    VideoFileClip = None
    TextClip = None
    CompositeVideoClip = None
    MOVIEPY_AVAILABLE = False

LOG_PATH = os.path.join(os.getcwd(), "l2s_font_debug.log")

def _log(msg: str):
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        try:
            print(f"{ts} | {msg}")
        except Exception:
            pass

# ---------------- Parsing helpers ----------------

def _srt_time_to_seconds(s: str) -> float:
    if not s or not isinstance(s, str):
        raise ValueError("Invalid SRT time string")
    try:
        s2 = s.strip().replace(".", ",")
        hh, mm, rest = s2.split(":", 2)
        if "," in rest:
            ss, ms = rest.split(",", 1)
        else:
            ss, ms = rest, "000"
        hh_i = int(hh); mm_i = int(mm); ss_i = int(ss); ms_i = int(ms[:3].ljust(3, "0"))
        return hh_i * 3600 + mm_i * 60 + ss_i + ms_i / 1000.0
    except Exception:
        # best-effort fallback
        try:
            return float(s.replace(",", "."))
        except Exception:
            raise

def _prepare_overlay_entries(srt_stub: Any) -> List[Dict[str, Any]]:
    if not srt_stub:
        return []
    if isinstance(srt_stub, list):
        out = []
        for item in srt_stub:
            if isinstance(item, dict):
                # allow both 'from'/'to' and 'start'/'end'
                if "from" in item and "to" in item:
                    try:
                        out.append({"start": _srt_time_to_seconds(item["from"]), "end": _srt_time_to_seconds(item["to"]), "text": item.get("text","")})
                        continue
                    except Exception:
                        pass
                if "start" in item and "end" in item:
                    try:
                        out.append({"start": float(item["start"]), "end": float(item["end"]), "text": item.get("text","")})
                        continue
                    except Exception:
                        pass
            if isinstance(item, str):
                blocks = re.split(r"\n\s*\n", item.strip())
                for b in blocks:
                    lines = [l.strip() for l in b.splitlines() if l.strip()]
                    time_line = None
                    text_lines = []
                    for ln in lines:
                        if "-->" in ln:
                            time_line = ln
                        else:
                            text_lines.append(ln)
                    if time_line:
                        try:
                            parts = [p.strip() for p in time_line.replace(",", ".").split("-->")]
                            st = _srt_time_to_seconds(parts[0]) if parts and parts[0] else None
                            en = _srt_time_to_seconds(parts[1]) if len(parts)>1 and parts[1] else None
                            out.append({"start": st, "end": en, "text": " ".join(text_lines)})
                        except Exception:
                            continue
        return out
    if isinstance(srt_stub, str):
        out = []
        blocks = re.split(r"\n\s*\n", srt_stub.strip())
        for b in blocks:
            lines = [l.strip() for l in b.splitlines() if l.strip()]
            time_line = None
            text_lines = []
            for ln in lines:
                if "-->" in ln:
                    time_line = ln
                else:
                    text_lines.append(ln)
            if time_line:
                try:
                    parts = [p.strip() for p in time_line.replace(",", ".").split("-->")]
                    st = _srt_time_to_seconds(parts[0]) if parts and parts[0] else None
                    en = _srt_time_to_seconds(parts[1]) if len(parts)>1 and parts[1] else None
                    out.append({"start": st, "end": en, "text": " ".join(text_lines)})
                except Exception:
                    continue
        return out
    return []

def normalize_overlay_instructions(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {"placement":"", "font":"", "size":{}, "color":"", "effects":[], "overlay_text":[]}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            raw = parsed
        except Exception:
            return {"placement":"", "font":"", "size":{}, "color":"", "effects":[], "overlay_text":[]}
    if not isinstance(raw, dict):
        return {"placement":"", "font":"", "size":{}, "color":"", "effects":[], "overlay_text":[]}
    out = dict(raw)
    out.setdefault("placement", out.get("placement",""))
    out.setdefault("font", out.get("font",""))
    out.setdefault("size", out.get("size", {}))
    out.setdefault("color", out.get("color","white"))
    out.setdefault("effects", out.get("effects", []))
    out.setdefault("overlay_text", out.get("overlay_text", []))
    return out

def _extract_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, (int,float)):
            return int(x)
        m = re.search(r"(-?\d+)", str(x))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None

# ---------------- Font & layout helpers ----------------

def _find_any_system_ttf(prefer_names: Optional[List[str]] = None) -> Optional[str]:
    try:
        if os.name == "nt":
            search_dirs = [r"C:\Windows\Fonts"]
        else:
            search_dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                           "/Library/Fonts", "/System/Library/Fonts"]
        prefer = [p.lower() for p in (prefer_names or [])]
        candidates = []
        for fd in search_dirs:
            if not fd or not os.path.isdir(fd):
                continue
            for root, _, files in os.walk(fd):
                for fn in files:
                    if fn.lower().endswith((".ttf", ".otf", ".ttc")):
                        candidates.append(os.path.join(root, fn))
        for p in prefer:
            for c in candidates:
                if p in os.path.basename(c).lower():
                    return c
        if candidates:
            return candidates[0]
    except Exception:
        pass
    return None

def _choose_font(font_name: Optional[str], size: int):
    if not PIL_AVAILABLE:
        return None
    try:
        if font_name:
            if os.path.isfile(str(font_name)):
                try:
                    return ImageFont.truetype(str(font_name), size=size)
                except Exception:
                    pass
            fp = _find_any_system_ttf([str(font_name)])
            if fp:
                try:
                    return ImageFont.truetype(fp, size=size)
                except Exception:
                    pass
            try:
                return ImageFont.truetype(str(font_name), size=size)
            except Exception:
                pass
    except Exception:
        pass
    for candidate in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf", "OpenSans-Regular.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    try:
        any_fp = _find_any_system_ttf(["arial", "dejavu", "liberation"])
        if any_fp:
            return ImageFont.truetype(any_fp, size=size)
    except Exception:
        pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None

def _size_name_to_pixels(size_val: Any, frame_h: Optional[int] = None, role: str = "step") -> int:
    if isinstance(size_val, (int,float)):
        return int(size_val)
    s = str(size_val).lower() if size_val else ""
    if frame_h is None:
        frame_h = 1920
    base_small = max(22, int(round(frame_h * 0.035)))
    base_medium = max(40, int(round(frame_h * 0.055)))
    base_large = max(64, int(round(frame_h * 0.09)))
    names = {"small": base_small, "medium": base_medium, "step": base_medium, "large": base_large}
    if s in names:
        return names[s]
    m = re.search(r"(\d{2,3})", s)
    if m:
        return int(m.group(1))
    return base_medium

def _fit_font_to_width(draw: ImageDraw.ImageDraw, text: str, font_family_guess, start_size: int, max_width: int, frame_h: int, min_px: int = 10) -> Tuple[Any,int]:
    txt = str(text or "")
    name_guess = None
    try:
        if font_family_guess and not hasattr(font_family_guess, "getmask"):
            name_guess = str(font_family_guess)
    except Exception:
        name_guess = None
    cur_size = int(start_size or max(12, frame_h//24))
    cur_size = max(cur_size, min_px)
    while cur_size >= min_px:
        font = _choose_font(name_guess, size=cur_size) if name_guess else _choose_font(None, size=cur_size)
        if font is None:
            font = ImageFont.load_default()
        words = txt.split()
        if not words:
            return font, cur_size
        lines = [words[0]]
        for w in words[1:]:
            test = lines[-1] + " " + w
            try:
                bbox = draw.textbbox((0,0), test, font=font)
                test_w = bbox[2] - bbox[0]
            except Exception:
                test_w = draw.textsize(test, font=font)[0]
            if test_w <= max_width:
                lines[-1] = test
            else:
                lines.append(w)
        max_w = 0
        for ln in lines:
            try:
                bbox = draw.textbbox((0,0), ln, font=font)
                wln = bbox[2]-bbox[0]
            except Exception:
                wln = draw.textsize(ln, font=font)[0]
            if wln > max_w:
                max_w = wln
        if max_w <= max_width:
            return font, cur_size
        cur_size -= 2
    return _choose_font(None, size=min_px) or ImageFont.load_default(), min_px

# ---------------- Drawing helpers (Pillow) ----------------

def _draw_boxed_wrapped_text_once(draw: ImageDraw.ImageDraw, x_center: int, y_top: int, txt: str, font, fill, bg_fill, max_box_width: int,
                                  padding: int = 8, shadow: bool = False, bold: bool = False, max_lines: Optional[int] = None) -> Tuple[int,int,int,int]:
    txt = str(txt or "")
    if max_box_width <= 0:
        max_box_width = 50
    # normalize fill and bg_fill to RGBA
    def _to_rgba(c):
        try:
            if isinstance(c, tuple) and len(c) in (3,4):
                if len(c)==3:
                    return (c[0],c[1],c[2],255)
                return tuple(c)
            if isinstance(c, str):
                try:
                    rgb = ImageColor.getrgb(c)
                    return (rgb[0], rgb[1], rgb[2], 255)
                except Exception:
                    pass
        except Exception:
            pass
        return (255,255,255,255)
    text_fill = _to_rgba(fill)
    bg_rgba = None
    if bg_fill:
        bg_rgba = _to_rgba(bg_fill)
        if len(bg_rgba)==3:
            bg_rgba = (bg_rgba[0], bg_rgba[1], bg_rgba[2], 230)
    cur_font = font
    min_font_px = 10
    # wrap function
    def _wrap(text, font, maxw):
        words = text.split()
        if not words:
            return [""]
        lines = []
        cur = words[0]
        for w in words[1:]:
            test = cur + " " + w
            try:
                bbox = draw.textbbox((0,0), test, font=font)
                test_w = bbox[2]-bbox[0]
            except Exception:
                test_w = draw.textsize(test, font=font)[0]
            if test_w <= maxw:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines
    for _ in range(8):
        lines = _wrap(txt, cur_font, max_box_width - padding*2)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while True:
                try:
                    bbox = draw.textbbox((0,0), last + "…", font=cur_font)
                    wlast = bbox[2]-bbox[0]
                except Exception:
                    wlast = draw.textsize(last + "…", font=cur_font)[0]
                if wlast <= (max_box_width - padding*2) or len(last)<=1:
                    lines[-1] = last + "…"
                    break
                last = last[:-1]
        too_wide = False
        for w in txt.split():
            try:
                bbox = draw.textbbox((0,0), w, font=cur_font)
                wpx = bbox[2]-bbox[0]
            except Exception:
                wpx = draw.textsize(w, font=cur_font)[0]
            if wpx > (max_box_width - padding*2):
                too_wide = True
                break
        if not too_wide:
            break
        new_size = max(min_font_px, getattr(cur_font, "size", 24) - 2)
        if new_size == getattr(cur_font, "size", None) or new_size <= min_font_px:
            break
        try:
            cur_font = _choose_font(None, size=new_size) or cur_font
        except Exception:
            break
    # measure
    max_w = 0
    heights = []
    for ln in lines:
        try:
            bbox = draw.textbbox((0,0), ln, font=cur_font)
            wln = bbox[2]-bbox[0]; hln = bbox[3]-bbox[1]
        except Exception:
            wln, hln = draw.textsize(ln, font=cur_font)
        max_w = max(max_w, wln)
        heights.append(hln)
    total_h = sum(heights) + 4*(len(lines)-1)
    box_w = max_w + padding*2
    box_h = total_h + padding*2
    x_pos = int(x_center - box_w//2)
    y_pos = int(y_top)
    if bg_rgba:
        draw.rectangle([x_pos, y_pos, x_pos+box_w, y_pos+box_h], fill=bg_rgba)
    cur_y = y_pos + padding
    for line in lines:
        try:
            bbox = draw.textbbox((0,0), line, font=cur_font)
            line_w = bbox[2]-bbox[0]; line_h = bbox[3]-bbox[1]
        except Exception:
            line_w, line_h = draw.textsize(line, font=cur_font)
        x_line = int(x_center - line_w//2)
        if shadow:
            try:
                draw.text((x_line+2, cur_y+2), line, font=cur_font, fill=(0,0,0,160))
            except Exception:
                pass
        if bold:
            offsets = [(0,0),(1,0),(0,1),(-1,0),(0,-1)]
            for ox,oy in offsets:
                draw.text((x_line+ox, cur_y+oy), line, font=cur_font, fill=text_fill)
        else:
            draw.text((x_line, cur_y), line, font=cur_font, fill=text_fill)
        cur_y += line_h + 4
    return box_w, box_h, x_pos, y_pos

# ---------------- Renderer (per-clip) ----------------

def apply_overlays_to_clip(clip_path: str, overlay_instructions: Dict[str,Any], srt_stub: Any, main_text: Optional[str] = None,
                           prefer_pillow: bool = True, keep_temp: bool = False) -> str:
    """
    Apply overlays/subtitles to a single finished vertical clip.
    Returns path to processed clip (original path replaced on success).
    """
    if not MOVIEPY_AVAILABLE:
        raise RuntimeError("moviepy is required for overlay rendering")
    entries = srt_stub if isinstance(srt_stub, list) else _prepare_overlay_entries(srt_stub)
    instr = normalize_overlay_instructions(overlay_instructions)
    overlay_list = instr.get("overlay_text", []) or []
    placement = instr.get("placement", "") or ""
    font_spec = instr.get("font", "") or ""
    color_spec = instr.get("color", "white") or ""
    size_map = instr.get("size", {}) or {}

    # MoviePy fallback path if PIL not available
    if not PIL_AVAILABLE:
        _log("PIL not available; using MoviePy TextClip fallback.")
        return _apply_overlays_moviepy_fallback(clip_path, instr, entries, main_text)

    clip = VideoFileClip(clip_path)
    fps = clip.fps

    def _to_str(v):
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            for k in ("text","value","label"):
                if k in v:
                    return _to_str(v[k])
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        return str(v)

    def _parse_time(v):
        if v is None:
            return None
        if isinstance(v, (int,float)):
            return float(v)
        try:
            return float(v)
        except Exception:
            try:
                return _srt_time_to_seconds(str(v))
            except Exception:
                return None

    def _compute_safe_zone(w,h):
        left = max(12, int(w * 0.05)); right = w - left
        top = max(10, int(h * 0.06)); bottom = max(int(h * 0.16), int(h * 0.14))
        return left, right, top, bottom

    def _placement_y(h, placement_str, th=0, role="subtitle"):
        ps = (placement_str or "").lower()
        if "top" in ps: return int(h*0.07)
        if "upper" in ps: return int(h*0.17)
        if "lower" in ps or "lower third" in ps: return int(h*0.55)
        if "bottom" in ps or "cta" in ps: return int(h*0.78)
        return int(h*0.82) if role == "subtitle" else int(h*0.5)

    def _get_font_for_ov(ov, default_role, frame_h, requested_size=None):
        fnt_name = _to_str(ov.get("font") if isinstance(ov, dict) else instr.get("font") or font_spec or "")
        if requested_size is not None:
            sz = requested_size
        elif ov.get("size") is not None:
            sz = _extract_int(ov.get("size")) or _size_name_to_pixels(ov.get("size"), frame_h=frame_h, role=default_role)
        else:
            if default_role == "hook":
                sz = _size_name_to_pixels(size_map.get("hook") or size_map.get("step") or "large", frame_h=frame_h, role="hook")
            else:
                sz = _size_name_to_pixels(size_map.get("step") or "medium", frame_h=frame_h, role="step")
        # reduced caps
        if default_role == "hook":
            max_px = max(18, int(frame_h * 0.08))
        else:
            max_px = max(14, int(frame_h * 0.06))
        min_px = 10
        sz = max(min_px, min(int(sz), max_px))
        font = _choose_font(fnt_name, size=int(sz)) or ImageFont.load_default()
        return font, int(sz)

    # Normalize overlay_list texts
    norm_overlay_list = []
    for ov in overlay_list:
        if isinstance(ov, dict):
            ovn = dict(ov)
            ovn["text"] = _to_str(ov.get("text",""))
            norm_overlay_list.append(ovn)
        else:
            norm_overlay_list.append({"text": _to_str(ov)})

    def make_frame(get_frame, t):
        frame = get_frame(t)
        try:
            arr = frame
            h, w = int(arr.shape[0]), int(arr.shape[1])
            left_safe, right_safe, top_safe, bottom_safe = _compute_safe_zone(w, h)
            usable_width = right_safe - left_safe - 16
            img = Image.fromarray(arr).convert("RGBA")
            draw = ImageDraw.Draw(img, "RGBA")

            # subtitle: single active entry
            active = None
            for e in entries:
                try:
                    st = _parse_time(e.get("start")); en = _parse_time(e.get("end"))
                    if st is None or en is None:
                        continue
                    if st <= t <= en:
                        active = e
                        break
                except Exception:
                    continue
            if active:
                try:
                    raw_txt = _to_str(active.get("text", ""))
                    # typewriter behavior: progressively reveal text based on entry timing.
                    try:
                        is_type = str(active.get("effect", "")).lower() == "typewriter"
                    except Exception:
                        is_type = False
                    if is_type:
                        try:
                            start = _parse_time(active.get("start")) or 0.0
                        except Exception:
                            start = 0.0
                        try:
                            end = _parse_time(active.get("end"))
                        except Exception:
                            end = None
                        # duration preference: explicit duration key, else end-start, else fallback
                        duration = None
                        try:
                            if active.get("duration") is not None:
                                duration = float(active.get("duration"))
                        except Exception:
                            duration = None
                        if duration is None and end is not None:
                            try:
                                duration = max(0.001, float(end) - float(start))
                            except Exception:
                                duration = None
                        if not duration:
                            duration = 2.5
                        # fraction of reveal 0..1
                        try:
                            frac = max(0.0, min(1.0, (float(t) - float(start)) / float(duration)))
                        except Exception:
                            frac = 1.0
                        mode = str(active.get("reveal_mode", "char") or "char").lower()
                        if mode == "word":
                            words = raw_txt.split()
                            n = int(round(len(words) * frac))
                            raw_txt = " ".join(words[:max(0, n)])
                        else:
                            # per-character reveal
                            n = int(round(len(raw_txt) * frac))
                            raw_txt = raw_txt[:max(0, n)]

                    # continue with font selection and draw
                    font, _sz = _get_font_for_ov(active, default_role="step", frame_h=h)
                    font, _ = _fit_font_to_width(draw, raw_txt, font, getattr(font, "size", _sz),
                                                 max(usable_width, 50), frame_h=h, min_px=10)
                    y = _placement_y(h, instr.get("placement", "bottom_center"), role="subtitle")
                    bg = active.get("background") or instr.get("background") or "black"
                    text_color = active.get("color") or instr.get("color") or color_spec or "white"
                    _draw_boxed_wrapped_text_once(draw, w // 2, y, raw_txt, font, fill=text_color, bg_fill=bg,
                                                  max_box_width=usable_width, padding=8, shadow=False, bold=False,
                                                  max_lines=2)
                except Exception as ex:
                    _log(f"subtitle draw error: {ex}")

            # overlays
            for ov in norm_overlay_list:
                try:
                    st = _parse_time(ov.get("start")); en = _parse_time(ov.get("end"))
                    if st is None and en is None:
                        show = True
                    elif st is None:
                        show = (t <= en)
                    elif en is None:
                        show = (t >= st)
                    else:
                        show = (st <= t <= en)
                    if not show:
                        continue

                    raw_txt = _to_str(ov.get("text", ""))

                    # typewriter reveal for overlays: use ov timing/effect keys
                    try:
                        is_type_ov = str(ov.get("effect", "")).lower() == "typewriter"
                    except Exception:
                        is_type_ov = False
                    if is_type_ov:
                        try:
                            start = _parse_time(ov.get("start")) or 0.0
                        except Exception:
                            start = 0.0
                        try:
                            end = _parse_time(ov.get("end"))
                        except Exception:
                            end = None
                        duration = None
                        try:
                            if ov.get("duration") is not None:
                                duration = float(ov.get("duration"))
                        except Exception:
                            duration = None
                        if duration is None and end is not None:
                            try:
                                duration = max(0.001, float(end) - float(start))
                            except Exception:
                                duration = None
                        if not duration:
                            duration = 2.5
                        try:
                            frac = max(0.0, min(1.0, (float(t) - float(start)) / float(duration)))
                        except Exception:
                            frac = 1.0
                        mode = str(ov.get("reveal_mode", "char") or "char").lower()
                        if mode == "word":
                            words = raw_txt.split()
                            n = int(round(len(words) * frac))
                            raw_txt = " ".join(words[:max(0, n)])
                        else:
                            n = int(round(len(raw_txt) * frac))
                            raw_txt = raw_txt[:max(0, n)]

                    pl = ov.get("placement") or placement or "top_center"
                    role = "hook"
                    font, _sz = _get_font_for_ov(ov, default_role=role, frame_h=h)
                    font, _ = _fit_font_to_width(draw, raw_txt, font, getattr(font, "size", _sz),
                                                 max(usable_width, 60), frame_h=h, min_px=10)
                    try:
                        bbox = draw.textbbox((0, 0), raw_txt, font=font)
                        th = bbox[3] - bbox[1]
                    except Exception:
                        th = draw.textsize(raw_txt, font=font)[1]
                    desired_y = _placement_y(h, pl, th=th, role=role)
                    if "top" in (pl or "").lower():
                        y = max(top_safe + 4, desired_y)
                    elif "bottom" in (pl or "").lower() or "cta" in (pl or "").lower():
                        y = min(desired_y, int(h - bottom_safe - th - 8))
                    else:
                        mid = int(h * 0.5 - th // 2)
                        y = max(top_safe, min(mid, int(h - bottom_safe - th - 8)))
                    bg = ov.get("background") or instr.get("background") or "black"
                    text_color = ov.get("color") or instr.get("color") or color_spec or "white"
                    style = str(ov.get("style", ""))
                    shadow = "shadow" in style or "drop" in style
                    bold = "bold" in style
                    _draw_boxed_wrapped_text_once(draw, w // 2, y, raw_txt, font, fill=text_color,
                                                  bg_fill=bg or "black", max_box_width=usable_width,
                                                  padding=10, shadow=shadow, bold=bold, max_lines=ov.get("max_lines"))
                except Exception as ex:
                    _log(f"overlay draw error: {ex}")
                    continue

            return np.array(img.convert("RGB"))
        except Exception as ex:
            _log(f"make_frame failure: {ex}")
            return frame
# ---------------- MoviePy fallback ----------------

def _apply_overlays_moviepy_fallback(clip_path: str, instr: Dict[str,Any], entries: List[Dict[str,Any]], main_text: Optional[str]) -> str:
    if not MOVIEPY_AVAILABLE:
        raise RuntimeError("moviepy required")
    clip = VideoFileClip(clip_path)
    w,h = clip.size
    overlay_clips = []
    subtitle_base = max(18, int(round(h*0.045))); subtitle_base = min(subtitle_base, 64)
    hook_base = max(24, int(round(h*0.06))); hook_base = min(hook_base, 120)
    def pos_for_role(role):
        if role == "hook": return ("center", int(h*0.12))
        if role == "subtitle": return ("center", int(h*0.85))
        return ("center", int(h*0.55))
    for e in entries:
        try:
            txt = e.get("text","")
            start = e.get("start", 0.0); end = e.get("end", None)
            if start is None or end is None:
                continue
            fontsize = _size_name_to_pixels(subtitle_base, frame_h=h, role="step")
            txtclip = TextClip(txt, fontsize=int(fontsize), color=instr.get("color","white"), font=None, method="caption")
            txtclip = txtclip.set_start(max(0.0, start)).set_duration(max(0.01, end-start))
            txtclip = txtclip.set_position(pos_for_role("subtitle"))
            overlay_clips.append(txtclip)
        except Exception:
            continue
    ov_list = instr.get("overlay_text",[]) or []
    for ov in ov_list:
        try:
            txt = ov.get("text","")
            start = ov.get("start", 0.0); end = ov.get("end", None)
            fontsize = _size_name_to_pixels(hook_base, frame_h=h, role="hook")
            txtclip = TextClip(txt, fontsize=int(fontsize), color=ov.get("color",instr.get("color","white")), font=None, method="caption")
            if end is None:
                txtclip = txtclip.set_start(0).set_duration(min(clip.duration,3.0))
            else:
                try:
                    txtclip = txtclip.set_start(max(0.0, float(start))).set_duration(max(0.01, float(end)-float(start)))
                except Exception:
                    txtclip = txtclip.set_start(0).set_duration(min(clip.duration,3.0))
            txtclip = txtclip.set_position(("center", int(h*0.12)))
            overlay_clips.append(txtclip)
        except Exception:
            continue
    if not overlay_clips and main_text:
        try:
            fontsize = _size_name_to_pixels(hook_base, frame_h=h, role="hook")
            txtclip = TextClip(main_text, fontsize=int(fontsize), color=instr.get("color","white"), font=None, method="caption")
            txtclip = txtclip.set_start(0).set_duration(min(3.0, clip.duration))
            txtclip = txtclip.set_position(("center", int(h*0.12)))
            overlay_clips.append(txtclip)
        except Exception:
            pass
    if not overlay_clips:
        return clip_path
    try:
        comp = CompositeVideoClip([clip] + overlay_clips)
        tmp_out = os.path.join(os.path.dirname(clip_path), "l2s_overlay_tmp.mp4")
        try:
            comp.write_videofile(tmp_out, codec="libx264", audio=True, fps=clip.fps, verbose=False, logger=None)
        except Exception:
            comp.write_videofile(tmp_out, codec="libx264", audio=True, fps=clip.fps)
        clip.close()
        try:
            os.replace(tmp_out, clip_path)
        except Exception:
            try:
                os.remove(clip_path)
            except Exception:
                pass
            os.rename(tmp_out, clip_path)
        return clip_path
    except Exception as ex:
        _log(f"moviepy overlay fallback failed: {ex}")
        raise

# ---------------- Queue processing ----------------

def apply_overlays_to_clip(clip_path: str, overlay_instructions: Dict[str,Any], srt_stub: Any, main_text: Optional[str] = None,
                           prefer_pillow: bool = True, keep_temp: bool = False) -> str:
    """
    Apply overlays/subtitles to a single finished vertical clip.
    Returns path to processed clip (original path replaced on success).
    """
    if not MOVIEPY_AVAILABLE:
        raise RuntimeError("moviepy is required for overlay rendering")
    entries = srt_stub if isinstance(srt_stub, list) else _prepare_overlay_entries(srt_stub)
    instr = normalize_overlay_instructions(overlay_instructions)
    overlay_list = instr.get("overlay_text", []) or []
    placement = instr.get("placement", "") or ""
    font_spec = instr.get("font", "") or ""
    color_spec = instr.get("color", "white") or ""
    size_map = instr.get("size", {}) or {}

    # MoviePy fallback path if PIL not available
    if not PIL_AVAILABLE:
        _log("PIL not available; using MoviePy TextClip fallback.")
        return _apply_overlays_moviepy_fallback(clip_path, instr, entries, main_text)

    clip = VideoFileClip(clip_path)
    fps = clip.fps

    def _to_str(v):
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            for k in ("text","value","label"):
                if k in v:
                    return _to_str(v[k])
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        return str(v)

    def _parse_time(v):
        if v is None:
            return None
        if isinstance(v, (int,float)):
            return float(v)
        try:
            return float(v)
        except Exception:
            try:
                return _srt_time_to_seconds(str(v))
            except Exception:
                return None

    def _compute_safe_zone(w,h):
        left = max(12, int(w * 0.05)); right = w - left
        top = max(10, int(h * 0.06)); bottom = max(int(h * 0.16), int(h * 0.14))
        return left, right, top, bottom

    def _placement_y(h, placement_str, th=0, role="subtitle"):
        ps = (placement_str or "").lower()
        if "top" in ps: return int(h*0.07)
        if "upper" in ps: return int(h*0.17)
        if "lower" in ps or "lower third" in ps: return int(h*0.55)
        if "bottom" in ps or "cta" in ps: return int(h*0.78)
        return int(h*0.82) if role == "subtitle" else int(h*0.5)

    def _get_font_for_ov(ov, default_role, frame_h, requested_size=None):
        fnt_name = _to_str(ov.get("font") if isinstance(ov, dict) else instr.get("font") or font_spec or "")
        if requested_size is not None:
            sz = requested_size
        elif ov.get("size") is not None:
            sz = _extract_int(ov.get("size")) or _size_name_to_pixels(ov.get("size"), frame_h=frame_h, role=default_role)
        else:
            if default_role == "hook":
                sz = _size_name_to_pixels(size_map.get("hook") or size_map.get("step") or "large", frame_h=frame_h, role="hook")
            else:
                sz = _size_name_to_pixels(size_map.get("step") or "medium", frame_h=frame_h, role="step")
        # reduced caps
        if default_role == "hook":
            max_px = max(18, int(frame_h * 0.08))
        else:
            max_px = max(14, int(frame_h * 0.06))
        min_px = 10
        sz = max(min_px, min(int(sz), max_px))
        font = _choose_font(fnt_name, size=int(sz)) or ImageFont.load_default()
        return font, int(sz)

    # Normalize overlay_list texts
    norm_overlay_list = []
    for ov in overlay_list:
        if isinstance(ov, dict):
            ovn = dict(ov)
            ovn["text"] = _to_str(ov.get("text",""))
            norm_overlay_list.append(ovn)
        else:
            norm_overlay_list.append({"text": _to_str(ov)})

    def make_frame(get_frame, t):
        frame = get_frame(t)
        try:
            arr = frame
            h, w = int(arr.shape[0]), int(arr.shape[1])
            left_safe, right_safe, top_safe, bottom_safe = _compute_safe_zone(w, h)
            usable_width = right_safe - left_safe - 16
            img = Image.fromarray(arr).convert("RGBA")
            draw = ImageDraw.Draw(img, "RGBA")

            # subtitle: single active entry
            active = None
            for e in entries:
                try:
                    st = _parse_time(e.get("start")); en = _parse_time(e.get("end"))
                    if st is None or en is None:
                        continue
                    if st <= t <= en:
                        active = e
                        break
                except Exception:
                    continue
            if active:
                try:
                    raw_txt = _to_str(active.get("text", ""))
                    # typewriter behavior: progressively reveal text based on entry timing.
                    try:
                        is_type = str(active.get("effect", "")).lower() == "typewriter"
                    except Exception:
                        is_type = False
                    if is_type:
                        try:
                            start = _parse_time(active.get("start")) or 0.0
                        except Exception:
                            start = 0.0
                        try:
                            end = _parse_time(active.get("end"))
                        except Exception:
                            end = None
                        # duration preference: explicit duration key, else end-start, else fallback
                        duration = None
                        try:
                            if active.get("duration") is not None:
                                duration = float(active.get("duration"))
                        except Exception:
                            duration = None
                        if duration is None and end is not None:
                            try:
                                duration = max(0.001, float(end) - float(start))
                            except Exception:
                                duration = None
                        if not duration:
                            duration = 2.5
                        # fraction of reveal 0..1
                        try:
                            frac = max(0.0, min(1.0, (float(t) - float(start)) / float(duration)))
                        except Exception:
                            frac = 1.0
                        mode = str(active.get("reveal_mode", "char") or "char").lower()
                        if mode == "word":
                            words = raw_txt.split()
                            n = int(round(len(words) * frac))
                            raw_txt = " ".join(words[:max(0, n)])
                        else:
                            # per-character reveal
                            n = int(round(len(raw_txt) * frac))
                            raw_txt = raw_txt[:max(0, n)]

                    # continue with font selection and draw
                    font, _sz = _get_font_for_ov(active, default_role="step", frame_h=h)
                    font, _ = _fit_font_to_width(draw, raw_txt, font, getattr(font, "size", _sz),
                                                 max(usable_width, 50), frame_h=h, min_px=10)
                    y = _placement_y(h, instr.get("placement", "bottom_center"), role="subtitle")
                    bg = active.get("background") or instr.get("background") or "black"
                    text_color = active.get("color") or instr.get("color") or color_spec or "white"
                    _draw_boxed_wrapped_text_once(draw, w // 2, y, raw_txt, font, fill=text_color, bg_fill=bg,
                                                  max_box_width=usable_width, padding=8, shadow=False, bold=False,
                                                  max_lines=2)
                except Exception as ex:
                    _log(f"subtitle draw error: {ex}")

            # overlays
            for ov in norm_overlay_list:
                try:
                    st = _parse_time(ov.get("start")); en = _parse_time(ov.get("end"))
                    if st is None and en is None:
                        show = True
                    elif st is None:
                        show = (t <= en)
                    elif en is None:
                        show = (t >= st)
                    else:
                        show = (st <= t <= en)
                    if not show:
                        continue

                    raw_txt = _to_str(ov.get("text", ""))

                    # typewriter reveal for overlays: use ov timing/effect keys
                    try:
                        is_type_ov = str(ov.get("effect", "")).lower() == "typewriter"
                    except Exception:
                        is_type_ov = False
                    if is_type_ov:
                        try:
                            start = _parse_time(ov.get("start")) or 0.0
                        except Exception:
                            start = 0.0
                        try:
                            end = _parse_time(ov.get("end"))
                        except Exception:
                            end = None
                        duration = None
                        try:
                            if ov.get("duration") is not None:
                                duration = float(ov.get("duration"))
                        except Exception:
                            duration = None
                        if duration is None and end is not None:
                            try:
                                duration = max(0.001, float(end) - float(start))
                            except Exception:
                                duration = None
                        if not duration:
                            duration = 2.5
                        try:
                            frac = max(0.0, min(1.0, (float(t) - float(start)) / float(duration)))
                        except Exception:
                            frac = 1.0
                        mode = str(ov.get("reveal_mode", "char") or "char").lower()
                        if mode == "word":
                            words = raw_txt.split()
                            n = int(round(len(words) * frac))
                            raw_txt = " ".join(words[:max(0, n)])
                        else:
                            n = int(round(len(raw_txt) * frac))
                            raw_txt = raw_txt[:max(0, n)]

                    pl = ov.get("placement") or placement or "top_center"
                    role = "hook"
                    font, _sz = _get_font_for_ov(ov, default_role=role, frame_h=h)
                    font, _ = _fit_font_to_width(draw, raw_txt, font, getattr(font, "size", _sz),
                                                 max(usable_width, 60), frame_h=h, min_px=10)
                    try:
                        bbox = draw.textbbox((0, 0), raw_txt, font=font)
                        th = bbox[3] - bbox[1]
                    except Exception:
                        th = draw.textsize(raw_txt, font=font)[1]
                    desired_y = _placement_y(h, pl, th=th, role=role)
                    if "top" in (pl or "").lower():
                        y = max(top_safe + 4, desired_y)
                    elif "bottom" in (pl or "").lower() or "cta" in (pl or "").lower():
                        y = min(desired_y, int(h - bottom_safe - th - 8))
                    else:
                        mid = int(h * 0.5 - th // 2)
                        y = max(top_safe, min(mid, int(h - bottom_safe - th - 8)))
                    bg = ov.get("background") or instr.get("background") or "black"
                    text_color = ov.get("color") or instr.get("color") or color_spec or "white"
                    style = str(ov.get("style", ""))
                    shadow = "shadow" in style or "drop" in style
                    bold = "bold" in style
                    _draw_boxed_wrapped_text_once(draw, w // 2, y, raw_txt, font, fill=text_color,
                                                  bg_fill=bg or "black", max_box_width=usable_width,
                                                  padding=10, shadow=shadow, bold=bold, max_lines=ov.get("max_lines"))
                except Exception as ex:
                    _log(f"overlay draw error: {ex}")
                    continue

            return np.array(img.convert("RGB"))
        except Exception as ex:
            _log(f"make_frame failure: {ex}")
            return frame

    # --- Apply the generated make_frame to the clip and write out the processed video ---
    try:
        processed = clip.fl(make_frame, apply_to=['video'])
        tmp_out = os.path.join(os.path.dirname(clip_path), "l2s_overlay_tmp.mp4")
        try:
            processed.write_videofile(tmp_out, codec="libx264", audio=True, fps=fps, verbose=False, logger=None)
        except Exception:
            # fallback to simpler call if logger options cause issues
            processed.write_videofile(tmp_out, codec="libx264", audio=True, fps=fps)
        # close both clip objects to release resources
        try:
            clip.close()
        except Exception:
            pass
        try:
            processed.close()
        except Exception:
            pass
        # replace original file with processed output
        try:
            os.replace(tmp_out, clip_path)
        except Exception:
            try:
                os.remove(clip_path)
            except Exception:
                pass
            os.rename(tmp_out, clip_path)
        return clip_path
    except Exception as ex:
        _log(f"overlay write failed: {ex}")
        # if requested, keep the temp file for debugging
        if keep_temp:
            _log(f"kept temp overlay output: {tmp_out}")
        raise
# ---------------- MoviePy fallback ----------------
    

def process_overlays_queue(queue_path: str, dry_run: bool = False, parallel: int = 1, keep_temp: bool = False):
    if not os.path.isfile(queue_path):
        raise FileNotFoundError(queue_path)
    with open(queue_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    entries = payload.get("entries", [])
    recipe_path = payload.get("recipe")
    print(f"[INFO] Processing overlay queue from recipe: {recipe_path}, entries={len(entries)}")

    # --- persistent promotion: ensure runner sees overlays generated by the GUI ---
    # Promote main_text or overlay_instructions.overlay_text to top-level overlay_text
    for entry in entries:
        if not entry.get("overlay_text"):
            if entry.get("main_text"):
                entry["overlay_text"] = entry["main_text"]
            else:
                oi = entry.get("overlay_instructions") or {}
                oi_ot = oi.get("overlay_text")
                if oi_ot:
                    entry["overlay_text"] = oi_ot
    # --- end promotion ---

    failures = []
    # worker wrapper
    def _worker(rec):
        out_path = rec.get("out_path")
        try:
            if not out_path or not os.path.isfile(out_path):
                return (out_path, "missing file")
            instr = rec.get("overlay_instructions", {}) or {}
            # ensure any promoted top-level overlay_text is visible inside instructions
            if rec.get("overlay_text"):
                # create a shallow copy so we don't mutate original structure unexpectedly
                instr = dict(instr)
                instr["overlay_text"] = rec.get("overlay_text")
            srt = rec.get("srt_for_clip", [])
            main_text = rec.get("main_text")
            # --- DEBUG: dump instruction shape so we can see why no overlays are applied ---
            try:
                # print a compact summary and the first overlay entry (if present)
                ot = instr.get("overlay_text")
                ot_summary = f"type={type(ot).__name__}, len={len(ot) if ot is not None and hasattr(ot,'__len__') else 'N/A'}"
                print(f"[DEBUG] apply_overlays_to_clip will receive instr keys: {list(instr.keys())}, overlay_text_summary: {ot_summary}")
                if ot and isinstance(ot, (list, tuple)) and len(ot) > 0:
                    # print the first overlay entry (safe truncate)
                    import json as _json
                    first = ot[0]
                    s = _json.dumps(first, ensure_ascii=False)
                    print(f"[DEBUG] overlay_text[0]: {s[:2000]}")
            except Exception:
                print("[DEBUG] failed to serialize overlay_text for debug")
            # --- end DEBUG ---

            if dry_run:
                return (out_path, "dry-run")
            apply_overlays_to_clip(out_path, instr, srt, main_text=main_text, prefer_pillow=True, keep_temp=keep_temp)
            return (out_path, None)
        except Exception as ex:
            return (out_path, str(ex))
    if parallel and parallel > 1:
        pool = multiprocessing.Pool(processes=parallel)
        results = pool.map(_worker, entries)
        pool.close(); pool.join()
        for out_path, err in results:
            if err:
                failures.append({"out_path": out_path, "reason": err})
    else:
        for rec in entries:
            out_path, err = _worker(rec)
            if err:
                failures.append({"out_path": out_path, "reason": err})
    print(f"[INFO] Overlay processing finished. failures={len(failures)}")
    if failures:
        for f in failures:
            _log(f"overlay failure: {f}")
    return failures


# ---------------- CLI ----------------

def _cli():
    p = argparse.ArgumentParser(description="Apply overlays/subtitles to finished vertical clips (post-processing).")
    p.add_argument("--queue", help="Path to overlay queue JSON written by l2s_core", required=False)
    p.add_argument("--recipe", help="Recipe JSON path (alternative to --queue)", required=False)
    p.add_argument("--outdir", help="If using --recipe, outdir where vertical clips were written", required=False)
    p.add_argument("--dry-run", action="store_true", help="Do not write changes, only report")
    p.add_argument("--parallel", type=int, default=1, help="Number of clips to process in parallel")
    p.add_argument("--keep-temp", action="store_true", help="Keep temp output files on failure for debugging")
    args = p.parse_args()
    if args.queue:
        return process_overlays_queue(args.queue, dry_run=args.dry_run, parallel=args.parallel, keep_temp=args.keep_temp)
    if args.recipe and args.outdir:
        with open(args.recipe, "r", encoding="utf-8") as f:
            recipe = json.load(f)
        clips = recipe.get("clips", [])
        queue_entries = []
        for clip_entry in clips:
            cid = clip_entry.get("id","")
            label = clip_entry.get("label","")
            safe_label = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in (label or "")).strip().replace(" ", "_")
            out_name = f"{cid}_{safe_label}.mp4" if safe_label else f"{cid}.mp4"
            out_path = os.path.join(args.outdir, out_name)
            raw_srt = clip_entry.get("subtitles") or clip_entry.get("srt_stub") or None
            srt_entries_abs = _prepare_overlay_entries(raw_srt) if raw_srt else []
            overlay_instructions_raw = clip_entry.get("overlay_instructions") or {}
            merged = overlay_instructions_raw if isinstance(overlay_instructions_raw, dict) else {}
            overlay_text = clip_entry.get("overlay_text") or clip_entry.get("text") or None
            if overlay_text:
                existing = merged.get("overlay_text") or []
                existing.append({"text": overlay_text})
                merged["overlay_text"] = existing
            overlay_instructions = normalize_overlay_instructions(merged)
            queue_entries.append({
                "id": cid,
                "out_path": out_path,
                "srt_for_clip": srt_entries_abs,
                "overlay_instructions": overlay_instructions,
                "main_text": clip_entry.get("overlay_text") or clip_entry.get("text")
            })
        payload = {"recipe": os.path.abspath(args.recipe), "created_at": datetime.datetime.utcnow().isoformat()+"Z", "entries": queue_entries}
        # write queue file to outdir for convenience
        queue_fname = os.path.join(args.outdir, f"overlays_queue_from_recipe_{os.path.splitext(os.path.basename(args.recipe))[0]}_{int(datetime.datetime.utcnow().timestamp())}.json")
        with open(queue_fname, "w", encoding="utf-8") as qf:
            json.dump(payload, qf, ensure_ascii=False, indent=2)
        print(f"[INFO] Overlay queue written: {queue_fname}")
        return process_overlays_queue(queue_fname, dry_run=args.dry_run, parallel=args.parallel, keep_temp=args.keep_temp)
    p.print_help()

if __name__ == "__main__":
    _cli()