#!/usr/bin/env python3
r"""
generate_recipe_ollama.py

Generator for recipe JSON with optional post-generation LLM edits (conversational refinements).
This module exposes:
- generate_recipe(...) -> (recipe_dict, log_lines)
- llm_edit_recipe(...) -> edited_recipe_dict

It is import-safe (can be imported by the GUI for in-process use).
CLI entrypoint remains available for standalone use.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# Optional HTTP client for Ollama
try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

# Optional moviepy for probing fallback
try:
    from moviepy.editor import VideoFileClip  # type: ignore
except Exception:
    VideoFileClip = None  # type: ignore

# ToT helper (expects tot_prompt_patch.py next to this file)
try:
    from tot_prompt_patch import get_tot_prompt
except Exception:
    def get_tot_prompt(tot_text: Optional[str] = None, include_default_if_empty: bool = True) -> str:
        return "" if not include_default_if_empty else "Follow this ToT: prioritize hooks, actions, clear labels, 3-5 clips 25-60s."

SAFETY_MARGIN = 0.05


# -------------------------
# Time helpers
# -------------------------
def parse_time_to_seconds(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    t = t.replace("mmm", "000")
    if "," in t and t.count(":") >= 2:
        main, ms = t.rsplit(",", 1)
        t = main + "." + ms
    else:
        t = t.replace(",", ".")
    parts = t.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            m, sec = parts
            return int(m) * 60.0 + float(sec)
        if len(parts) >= 3:
            h = int(parts[-3]); m = int(parts[-2]); sec = float(parts[-1])
            return h * 3600.0 + m * 60.0 + sec
    except Exception:
        try:
            return float(t)
        except Exception:
            return None
    return None


def seconds_to_hhmmss(s: float) -> str:
    s = max(0.0, float(s))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def seconds_to_hhmmss_ms(s: float) -> str:
    s = max(0.0, float(s))
    hours = int(s // 3600)
    minutes = int((s % 3600) // 60)
    secs = int(s % 60)
    ms = int(round((s - int(s)) * 1000))
    if ms >= 1000:
        secs += 1
        ms -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


# -------------------------
# Video duration probing
# -------------------------
def probe_video_duration_ffprobe(path: str) -> Optional[float]:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (proc.stdout or "").strip()
        if out:
            return float(out)
    except Exception:
        pass
    return None


def probe_video_duration_moviepy(path: str) -> Optional[float]:
    if VideoFileClip is None:
        return None
    try:
        clip = VideoFileClip(path)
        dur = float(clip.duration)
        try:
            clip.reader.close()
        except Exception:
            pass
        if clip.audio:
            try:
                clip.audio.reader.close_proc()
            except Exception:
                pass
        return dur
    except Exception:
        return None


def get_video_duration(path: str) -> Optional[float]:
    d = probe_video_duration_ffprobe(path)
    if d is not None:
        return d
    return probe_video_duration_moviepy(path)


# -------------------------
# Transcript grouping loader
# -------------------------
def is_noise_text(txt: str) -> bool:
    if not txt:
        return True
    t = txt.strip()
    if not t:
        return True
    low = t.lower()
    if low.startswith("[") and low.endswith("]"):
        return True
    digits_only = all(ch.isdigit() or ch in " :.,-" for ch in t)
    if digits_only and len([c for c in t if c.isalpha()]) == 0:
        return True
    return False


def load_transcript_grouped(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        lines = [ln.rstrip("\n\r") for ln in fh]

    items: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue
        parts = ln.split()
        first = parts[0] if parts else ""
        ts = parse_time_to_seconds(first)
        remainder = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        if ts is not None and remainder:
            text = remainder
            items.append({"start": ts, "text": text if not is_noise_text(text) else ""})
            i += 1
            continue
        if ts is not None and not remainder:
            j = i + 1
            text_lines: List[str] = []
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                nxt_parts = nxt.split()
                nxt_first = nxt_parts[0] if nxt_parts else ""
                nxt_ts = parse_time_to_seconds(nxt_first)
                if nxt_ts is not None:
                    break
                text_lines.append(nxt)
                j += 1
            text = " ".join(text_lines).strip()
            items.append({"start": ts, "text": text if text and not is_noise_text(text) else ""})
            i = j
            continue
        if not is_noise_text(ln):
            items.append({"start": None, "text": ln})
        i += 1
    return items


# -------------------------
# Build subtitles from grouped transcript
# -------------------------
def build_subtitles_from_transcript_blocks(blocks: List[Dict[str, Any]], clip_start: float, clip_end: float) -> List[Dict[str, Any]]:
    timed = [b for b in blocks if b.get("start") is not None and (b.get("text") or "").strip()]
    timed = sorted(timed, key=lambda x: x["start"])
    subs: List[Dict[str, Any]] = []
    for idx, b in enumerate(timed):
        s = float(b["start"])
        if s < clip_start - 0.001 or s > clip_end + 0.001:
            continue
        next_start = timed[idx + 1]["start"] if idx + 1 < len(timed) else None
        if next_start and next_start > s + 0.2:
            e = min(next_start - 0.05, clip_end - 0.001)
        else:
            txt_len = len(str(b.get("text") or ""))
            base = 4.0 + min(8.0, txt_len / 20.0)
            e = min(s + base, clip_end - 0.001)
        if e <= s:
            e = min(clip_end - 0.001, s + 1.0)
            if e <= s:
                continue
        subs.append({"from": seconds_to_hhmmss_ms(s), "to": seconds_to_hhmmss_ms(e), "text": " ".join(str(b.get("text") or "").split())})
    return subs


# -------------------------
# Robust JSON extraction from model output
# -------------------------
def extract_first_json_object(s: str) -> Tuple[Optional[str], Optional[str]]:
    if not s:
        return None, None
    start = s.find("{")
    if start == -1:
        return None, None
    i = start
    depth = 0
    in_str = False
    esc = False
    while i < len(s):
        ch = s[i]
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"' and not esc:
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1], s[i + 1:]
        i += 1
    return None, None


def try_parse_json_from_model_output(text: str) -> Any:
    txt = text.strip()
    try:
        return json.loads(txt)
    except Exception:
        obj_text, _ = extract_first_json_object(text)
        if obj_text:
            try:
                return json.loads(obj_text)
            except Exception as ex:
                raise ValueError(f"Failed to parse extracted JSON object: {ex}\nSnippet head:\n{obj_text[:2000]}")
        raise ValueError(f"Could not parse JSON from model output. Output head:\n{txt[:2000]}")


# -------------------------
# Clip normalization & clamping
# -------------------------
def clamp_and_normalize_clip(clip: Dict[str, Any],
                             video_duration: Optional[float],
                             transcript_blocks: Optional[List[Dict[str, Any]]] = None,
                             prefer_transcript_subs: bool = False,
                             min_clip_len: float = 3.0,
                             verbose: bool = False) -> Dict[str, Any]:
    def to_seconds_field(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            return parse_time_to_seconds(v)
        return None

    start_s = to_seconds_field(clip.get("start"))
    end_s = to_seconds_field(clip.get("end"))
    dur = clip.get("duration_sec") or clip.get("duration")
    dur_s = float(dur) if dur is not None else None

    if end_s is None and start_s is not None and dur_s is not None:
        end_s = start_s + dur_s
    if start_s is None and end_s is not None and dur_s is not None:
        start_s = end_s - dur_s
    if start_s is None:
        start_s = 0.0
    if end_s is None:
        end_s = start_s + max(min_clip_len, dur_s or 10.0)

    if video_duration is not None:
        max_allowed_end = max(0.0, video_duration - SAFETY_MARGIN)
        if end_s > max_allowed_end:
            if verbose:
                print(f"[WARNING] Clip end ({end_s:.3f}s) > video duration ({video_duration:.3f}s). Clamping to {max_allowed_end:.3f}s", file=sys.stderr)
            end_s = max_allowed_end
        if start_s >= end_s:
            suggested = max(0.0, end_s - max(min_clip_len, dur_s or 3.0))
            if verbose:
                print(f"[WARNING] Adjusting start {start_s:.3f}s -> {suggested:.3f}s", file=sys.stderr)
            start_s = suggested

    if (end_s - start_s) < min_clip_len:
        if video_duration is not None:
            end_s = min(video_duration - SAFETY_MARGIN, start_s + min_clip_len)
        else:
            end_s = start_s + min_clip_len

    duration_seconds = max(0.0, end_s - start_s)
    duration_sec_int = int(round(duration_seconds))

    # subtitles
    subs: List[Dict[str, Any]] = []
    if prefer_transcript_subs and transcript_blocks:
        subs = build_subtitles_from_transcript_blocks(transcript_blocks, start_s, end_s)
    else:
        subs_in = clip.get("subtitles") or []
        parsed: List[Dict[str, Any]] = []
        for s in subs_in:
            if isinstance(s, dict):
                sf = to_seconds_field(s.get("from") or s.get("start"))
                ef = to_seconds_field(s.get("to") or s.get("end"))
                txt = s.get("text") or ""
            else:
                sf = None; ef = None; txt = str(s)
            parsed.append({"start": sf, "end": ef, "text": txt})
        cursor = start_s + 0.5
        preserved: List[Dict[str, Any]] = []
        for p in parsed:
            sf, ef, txt = p["start"], p["end"], p["text"]
            if sf is None and ef is None:
                window = min(5.0, max(2.0, duration_seconds / max(6.0, len(parsed))))
                sf = cursor; ef = min(end_s - 0.001, sf + window); cursor = ef + 0.5
                if sf >= end_s:
                    ef = end_s - 0.001; sf = max(start_s + 0.001, ef - window)
            elif sf is None:
                sf = max(start_s + 0.001, ef - 4.0)
            elif ef is None:
                ef = min(end_s - 0.001, sf + 4.0)
            if sf < start_s: sf = start_s + 0.001
            if ef > end_s: ef = end_s - 0.001
            if ef <= sf:
                ef = min(end_s - 0.001, sf + 1.0)
                if ef <= sf:
                    continue
            preserved.append({"from": seconds_to_hhmmss_ms(sf), "to": seconds_to_hhmmss_ms(ef), "text": " ".join(str(txt).split())})
        subs = preserved

    if not subs:
        mid = start_s + max(1.0, duration_seconds / 3.0)
        subs = [{"from": seconds_to_hhmmss_ms(mid), "to": seconds_to_hhmmss_ms(min(end_s - 0.001, mid + 5.0)), "text": "Sample subtitle text."}]

    normalized = dict(clip)
    normalized["start"] = seconds_to_hhmmss(start_s)
    normalized["end"] = seconds_to_hhmmss(end_s)
    normalized["duration_sec"] = duration_sec_int
    normalized["subtitles"] = subs
    return normalized


# -------------------------
# Fallback recipe builder
# -------------------------
def build_fallback_recipe(src_path: str, transcript_blocks: List[Dict[str, Any]], video_duration: Optional[float] = None, verbose: bool = False) -> Dict[str, Any]:
    candidate_starts = [b["start"] for b in transcript_blocks if b.get("start") is not None and (b.get("text") or "").strip()]
    if candidate_starts:
        start = float(candidate_starts[0])
        end_candidates = [b["start"] for b in transcript_blocks if b.get("start") is not None and b["start"] > start and (b.get("text") or "").strip()]
        if end_candidates:
            end = float(end_candidates[min(len(end_candidates)-1, 4)])
        else:
            end = start + 120.0
    else:
        start = 83.0
        end = start + 117.0

    if video_duration is not None:
        end = min(end, max(0.0, video_duration - SAFETY_MARGIN))
        if end <= start:
            start = max(0.0, end - 117.0)

    duration_sec = int(round(end - start))
    clip = OrderedDict([
        ("id", "01"),
        ("label", "Sample Clip"),
        ("start", seconds_to_hhmmss(start)),
        ("end", seconds_to_hhmmss(end)),
        ("duration_sec", duration_sec),
        ("overlay_text", [
            {
                "text": "Key Moment",
                "placement": "top_center",
                "font": "Open Sans",
                "size": "medium",
                "style": "bold_drop_shadow",
                "effect": "typewriter",
                "color": "#ffffff",
                "background": "#063078"
            }
        ])
    ])

    subs = build_subtitles_from_transcript_blocks(transcript_blocks, start, end)
    if subs:
        clip["subtitles"] = subs
    else:
        clip["subtitles"] = [
            {"from": seconds_to_hhmmss_ms(start + 5.0), "to": seconds_to_hhmmss_ms(start + 10.0), "text": "Sample subtitle text."}
        ]

    recipe = OrderedDict([
        ("src", os.path.abspath(src_path)),
        ("style_profile", "educational"),
        ("generate_thumbnails", False),
        ("add_text_overlay", True),
        ("multi_platform", True),
        ("platforms", ["vertical", "square", "landscape"]),
        ("caption_style", {
            "placement": "bottom_center", "font": "Roboto", "size": "small", "style": "",
            "effect": "line_by_line_fade", "color": "#ffffff", "background": "#000000"
        }),
        ("highlight_style", {
            "placement": "top_center", "font": "Open Sans", "size": "medium", "style": "bold_drop_shadow",
            "effect": "typewriter", "color": "#ffd600", "background": "#000000"
        }),
        ("clips", [clip])
    ])
    return recipe


# -------------------------
# LLM-based post-generation edit (conversational refinement)
# -------------------------
def llm_edit_recipe(recipe: Dict[str, Any],
                    instruction: str,
                    model: str = "llama2",
                    use_http: bool = True,
                    video_duration: Optional[float] = None,
                    transcript_blocks: Optional[List[Dict[str, Any]]] = None,
                    tot_text: Optional[str] = None,
                    include_default_tot: bool = False,
                    verbose: bool = False) -> Dict[str, Any]:
    """
    Send current recipe + instruction to the local Ollama model and request an edited recipe JSON.
    Returns the edited recipe dict.
    """
    if not instruction or not instruction.strip():
        raise ValueError("No instruction provided for LLM edit.")

    tot_block = get_tot_prompt(tot_text, include_default_if_empty=include_default_tot)
    system = (
        (tot_block + "\n\n") if tot_block else ""
    ) + (
        "You are Video Ops Mentor. You will ONLY return a single JSON object (no surrounding text, no explanations). "
        "The JSON must follow the schema of the input recipe and preserve required keys: src, clips, caption_style, highlight_style, platforms, multi_platform. "
        "Each clip must include start (HH:MM:SS), end (HH:MM:SS), duration_sec (int), and subtitles array where each subtitle has from (HH:MM:SS,mmm), to (HH:MM:SS,mmm), and text. "
        "Do not change recipe['src'] or any file paths. Do not invent new top-level keys. If you cannot follow the instruction, return the original JSON unchanged."
    )

    payload_prompt = system + "\n\nINPUT_RECIPE:\n" + json.dumps(recipe, ensure_ascii=False, indent=2) + "\n\nINSTRUCTION:\n" + instruction + "\n\nReturn the updated full JSON recipe only."

    # Try HTTP Ollama first
    text_out: Optional[str] = None
    try:
        if use_http and requests is not None:
            url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/generate"
            r = requests.post(url, json={"model": model, "prompt": payload_prompt, "maxTokens": 2000}, timeout=90)
            r.raise_for_status()
            text_out = r.text
            if verbose:
                print("[DEBUG] Received response from Ollama HTTP API for edit", file=sys.stderr)
    except Exception:
        text_out = None

    # Fallback to Ollama CLI
    if text_out is None:
        try:
            proc = subprocess.run(["ollama", "run", model, payload_prompt], capture_output=True, text=True, timeout=120)
            text_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if verbose:
                print("[DEBUG] Received response from Ollama CLI for edit", file=sys.stderr)
        except Exception as ex:
            raise ValueError(f"Failed to run Ollama for edit: {ex}")

    # Parse the LLM output into JSON robustly
    parsed = try_parse_json_from_model_output(text_out)
    if not isinstance(parsed, dict):
        raise ValueError("LLM edit did not return a JSON object as expected.")

    # Basic validation
    if "clips" not in parsed or not isinstance(parsed["clips"], list):
        raise ValueError("Edited recipe missing valid 'clips' list.")

    # Ensure src preserved
    parsed["src"] = recipe.get("src")

    # Normalize & clamp each clip
    processed_clips: List[Dict[str, Any]] = []
    for c in parsed.get("clips", []):
        try:
            norm = clamp_and_normalize_clip(c,
                                            video_duration if video_duration is not None else None,
                                            transcript_blocks if transcript_blocks is not None else None,
                                            prefer_transcript_subs=bool(transcript_blocks),
                                            min_clip_len=3.0,
                                            verbose=verbose)
            processed_clips.append(norm)
        except Exception as e:
            if verbose:
                print(f"[DEBUG] Skipping invalid edited clip: {e}", file=sys.stderr)
            continue

    if not processed_clips:
        raise ValueError("After normalization, no valid clips remained in edited recipe.")

    parsed["clips"] = processed_clips

    # Ensure top-level keys preserved if missing
    for k in ["caption_style", "highlight_style", "platforms", "multi_platform", "style_profile", "generate_thumbnails", "add_text_overlay"]:
        if k not in parsed and k in recipe:
            parsed[k] = recipe[k]

    return parsed


# -------------------------
# Helpers: compact small lists for visual match
# -------------------------
def compact_platforms_inline(json_text: str) -> str:
    key = '"platforms": ['
    idx = json_text.find(key)
    if idx == -1:
        return json_text
    start = idx + len(key) - 1
    i = start
    depth = 0
    in_str = False
    esc = False
    while i < len(json_text):
        ch = json_text[i]
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"' and not esc:
            in_str = not in_str
        elif not in_str:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        i += 1
    else:
        return json_text
    block = json_text[idx: end + 1]
    try:
        arr_text = block[block.find("["):].strip()
        arr = json.loads(arr_text)
        if isinstance(arr, list) and 0 < len(arr) <= 10 and all(isinstance(x, str) and len(x) < 30 for x in arr):
            inline = '"platforms": [' + ", ".join(json.dumps(x) for x in arr) + ']'
            return json_text[:idx] + inline + json_text[end + 1:]
    except Exception:
        pass
    return json_text


# -------------------------
# High-level API: generate_recipe (callable from GUI)
# -------------------------
def generate_recipe(src: str,
                    transcript: str,
                    out: Optional[str] = None,
                    model: str = "llama2",
                    max_clips: int = 4,
                    min_duration: int = 25,
                    max_duration: int = 60,
                    per_clip_platforms: bool = False,
                    single_methods_clip: bool = False,
                    tot_text: Optional[str] = None,
                    include_default_tot: bool = True,
                    use_http: bool = True,
                    verbose: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    """
    High-level function to generate a recipe dict from source + transcript.
    Returns (recipe_dict, log_lines). If out is provided, writes JSON to out.
    This function is safe to call from other Python code (e.g. the GUI).
    """
    logs: List[str] = []
    def log(s: str):
        logs.append(s)
        if verbose:
            print(s, file=sys.stderr)

    if not os.path.isfile(src):
        raise FileNotFoundError(f"Source video not found: {src}")
    transcript_blocks = load_transcript_grouped(transcript)
    log(f"[INFO] Loaded {len(transcript_blocks)} transcript blocks")

    video_duration = get_video_duration(src)
    log(f"[DEBUG] Probed video duration: {video_duration}")

    prefer_transcript_subs = sum(1 for b in transcript_blocks if b.get("start") is not None) >= 5
    log(f"[DEBUG] prefer_transcript_subs={prefer_transcript_subs}")

    segments_text = "\n".join(f"{i+1}. [{seconds_to_hhmmss(b['start']) if b.get('start') is not None else 'UNKNOWN'}] {b.get('text','')}" for i, b in enumerate(transcript_blocks[:200]))

    base_system = "You are Video Ops Mentor. Return a JSON recipe with a 'clips' array. Use HH:MM:SS and HH:MM:SS,mmm formats."
    tot_block = get_tot_prompt(tot_text, include_default_if_empty=include_default_tot)
    system_instructions = (tot_block + "\n\n" + base_system) if tot_block else base_system
    user_prompt = f"Transcript blocks:\n{segments_text}\n\nProduce a JSON recipe with clip suggestions (clips array) following the ToT above."

    # Query LLM (HTTP if available and desired)
    model_output_text: Optional[str] = None
    try:
        use_http_env = os.environ.get("OLLAMA_USE_HTTP", "").strip() == "1"
        if requests is not None and use_http and not use_http_env:
            try:
                url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/generate"
                payload = {"model": model, "prompt": system_instructions + "\n\n" + user_prompt, "maxTokens": 2000}
                r = requests.post(url, json=payload, timeout=30)
                r.raise_for_status()
                model_output_text = r.text
                log("[DEBUG] Received response from Ollama HTTP API")
            except Exception as e:
                log(f"[DEBUG] Ollama HTTP failed: {e}")
                model_output_text = None
        if model_output_text is None:
            candidates = [
                ["ollama", "run", model, system_instructions + "\n\n" + user_prompt],
                ["ollama", "run", model, system_instructions],
                ["ollama", "run", model],
                ["ollama", "chat", model, system_instructions + "\n\n" + user_prompt],
                ["ollama", "chat", model]
            ]
            for cmd in candidates:
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
                    if out and out.strip():
                        model_output_text = out
                        log(f"[DEBUG] Received response from Ollama CLI (cmd: {' '.join(cmd[:3])}...)")
                        break
                except FileNotFoundError:
                    break
                except Exception:
                    continue
    except Exception as ex:
        log(f"[DEBUG] Ollama request failed: {ex}")
        model_output_text = None

    recipe: Dict[str, Any]
    if model_output_text:
        try:
            parsed = try_parse_json_from_model_output(model_output_text)
            if isinstance(parsed, dict) and parsed.get("clips"):
                processed_clips: List[Dict[str, Any]] = []
                for clip in parsed.get("clips", []):
                    try:
                        norm = clamp_and_normalize_clip(clip, video_duration, transcript_blocks, prefer_transcript_subs, min_clip_len=max(3.0, float(min_duration)), verbose=verbose)
                        processed_clips.append(norm)
                    except Exception as e:
                        log(f"[DEBUG] Failed to normalize a clip: {e}")
                        continue
                recipe = OrderedDict(parsed)
                recipe["clips"] = processed_clips
                if not recipe.get("src"):
                    recipe["src"] = os.path.abspath(src)
                log("[INFO] Parsed recipe from LLM output")
            else:
                log("[DEBUG] Model output did not contain a 'clips' list; falling back.")
                recipe = build_fallback_recipe(src, transcript_blocks, video_duration=video_duration, verbose=verbose)
        except Exception as e:
            log(f"[DEBUG] Failed to parse model output JSON: {e}")
            recipe = build_fallback_recipe(src, transcript_blocks, video_duration=video_duration, verbose=verbose)
    else:
        log("[INFO] No LLM output; using fallback recipe")
        recipe = build_fallback_recipe(src, transcript_blocks, video_duration=video_duration, verbose=verbose)

    # post-process deterministic single-methods clip if requested
    if single_methods_clip:
        DEFAULT_METHOD_KEYWORDS = [
            "method 1", "method1", "method 2", "method2", "method 3", "method3",
            "file", "vice", "bench grinder", "bank grinder", "handheld grinder", "grinder",
            "clamp the blade"
        ]
        def find_methods_range(blocks: List[Dict[str, Any]], keywords: Optional[List[str]] = None) -> Optional[Tuple[int, int]]:
            if not blocks:
                return None
            kws = [k.lower() for k in (keywords or DEFAULT_METHOD_KEYWORDS)]
            matched_indices = []
            for i, b in enumerate(blocks):
                txt = (b.get("text") or "").lower()
                if not txt:
                    continue
                for k in kws:
                    if k in txt:
                        matched_indices.append(i)
                        break
            if not matched_indices:
                return None
            return (min(matched_indices), max(matched_indices))

        rng = find_methods_range(transcript_blocks)
        if rng:
            first_idx, last_idx = rng
            start_s = transcript_blocks[first_idx].get("start") or 0.0
            if last_idx + 1 < len(transcript_blocks) and transcript_blocks[last_idx + 1].get("start") is not None:
                end_s = transcript_blocks[last_idx + 1]["start"]
            else:
                end_s = start_s + 120.0
            start_s = max(0.0, float(start_s) - 2.0)
            end_s = float(end_s) + 2.0
            if video_duration is not None:
                end_s = min(end_s, max(0.0, video_duration - SAFETY_MARGIN))
            clip = {
                "id": "01",
                "label": "Selected Methods",
                "start": seconds_to_hhmmss(start_s),
                "end": seconds_to_hhmmss(end_s),
                "duration_sec": int(round(max(0.0, end_s - start_s))),
                "overlay_text": [{
                    "text": "Key Methods",
                    "placement": "top_center", "font": "Open Sans", "size": "medium",
                    "style": "bold_drop_shadow", "effect": "typewriter", "color": "#ffffff", "background": "#063078"
                }]
            }
            subs = build_subtitles_from_transcript_blocks(transcript_blocks, start_s, end_s)
            if subs:
                clip["subtitles"] = subs
            recipe["clips"] = [clamp_and_normalize_clip(clip, video_duration, transcript_blocks, prefer_transcript_subs=True, min_clip_len=max(3.0, float(min_duration)), verbose=verbose)]
            log("[INFO] Applied deterministic single-methods clip override")

    # If out provided, write file
    ordered_recipe = OrderedDict()
    ordered_recipe["src"] = os.path.abspath(recipe.get("src") or src)
    ordered_recipe["style_profile"] = recipe.get("style_profile", "educational")
    ordered_recipe["generate_thumbnails"] = recipe.get("generate_thumbnails", False)
    ordered_recipe["add_text_overlay"] = recipe.get("add_text_overlay", True)
    ordered_recipe["multi_platform"] = recipe.get("multi_platform", True)
    ordered_recipe["platforms"] = recipe.get("platforms", ["vertical", "square", "landscape"])
    ordered_recipe["caption_style"] = recipe.get("caption_style", {"placement": "bottom_center", "font": "Roboto", "size": "small", "style": "", "effect": "line_by_line_fade", "color": "#ffffff", "background": "#000000"})
    ordered_recipe["highlight_style"] = recipe.get("highlight_style", {"placement": "top_center", "font": "Open Sans", "size": "medium", "style": "bold_drop_shadow", "effect": "typewriter", "color": "#ffd600", "background": "#000000"})
    ordered_recipe["clips"] = recipe.get("clips", [])

    if per_clip_platforms:
        for c in ordered_recipe["clips"]:
            if "platforms" not in c:
                c["platforms"] = ordered_recipe["platforms"][:]
            c["multi_platform"] = True

    raw = json.dumps(ordered_recipe, ensure_ascii=False, indent=2)
    raw = compact_platforms_inline(raw)
    if out:
        out_dir = os.path.dirname(os.path.abspath(out))
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(raw)
        log(f"[INFO] Recipe JSON written to {out}")

    return ordered_recipe, logs


# -------------------------
# CLI entrypoint (keeps original CLI)
# -------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate recipe JSON using a local Ollama model from a transcript + source video.")
    parser.add_argument("--src", required=True, help="Absolute path to source video file.")
    parser.add_argument("--transcript", required=True, help="Path to transcript file (JSON array or plain text).")
    parser.add_argument("--out", required=True, help="Path to write generated recipe JSON.")
    parser.add_argument("--model", default="llama2", help="Ollama model name to use (local).")
    parser.add_argument("--max-clips", dest="max_clips", type=int, default=4, help="Max number of clips requested.")
    parser.add_argument("--min-duration", dest="min_duration", type=int, default=25, help="Minimum clip duration (seconds).")
    parser.add_argument("--max-duration", dest="max_duration", type=int, default=60, help="Maximum clip duration (seconds).")
    parser.add_argument("--per-clip-platforms", action="store_true", help="If set, include per-clip platforms (default OFF to match original).")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--single-methods-clip", action="store_true", help="Build a single clip covering detected methods in transcript.")
    parser.add_argument("--edit", "--followup", dest="edit_instruction", help="A follow-up instruction for the LLM to edit the generated recipe JSON (JSON-only response expected).")
    parser.add_argument("--tot", dest="tot_text", help="Optional multi-line ToT text to instruct the LLM how to choose clips (overrides built-in).")
    parser.add_argument("--use-default-tot", action="store_true", help="Include the internal generic ToT template in the LLM prompt (alias; default unless --no-default-tot).")
    parser.add_argument("--no-default-tot", action="store_true", help="Do NOT include the internal generic ToT template in the LLM prompt.")
    args = parser.parse_args(argv)

    include_default = not bool(args.no_default_tot)
    if args.use_default_tot:
        include_default = True

    try:
        recipe, logs = generate_recipe(
            src=args.src,
            transcript=args.transcript,
            out=args.out,
            model=args.model,
            max_clips=args.max_clips,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            per_clip_platforms=args.per_clip_platforms,
            single_methods_clip=args.single_methods_clip,
            tot_text=args.tot_text,
            include_default_tot=include_default,
            use_http=True,
            verbose=args.verbose
        )
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    # If edit requested, run llm_edit_recipe synchronously and overwrite out
    if args.edit_instruction:
        try:
            edited = llm_edit_recipe(recipe,
                                    args.edit_instruction,
                                    model=args.model,
                                    use_http=True,
                                    video_duration=get_video_duration(args.src),
                                    transcript_blocks=load_transcript_grouped(args.transcript),
                                    tot_text=args.tot_text,
                                    include_default_tot=include_default,
                                    verbose=args.verbose)
            # write edited recipe to out
            raw = json.dumps(edited, ensure_ascii=False, indent=2)
            raw = compact_platforms_inline(raw)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(raw)
            print(f"[INFO] Edited recipe JSON written to {args.out}")
        except Exception as e:
            print(f"[ERROR] LLM edit failed: {e}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())