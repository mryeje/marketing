#!/usr/bin/env python3
"""
generate_recipe.py

Enhanced generator that forces the Llama model to refer to supplied source passages.

Key features added/updated:
- Chunk transcript into timestamped passages.
- Naive retrieval (token overlap) to select top-k relevant passages.
- Build a strict prompt that includes only retrieved passages and a "contract" requiring:
  - JSON-only output
  - Per-clip "sources" array with {doc_id, start, end, quote} where quote must be an exact substring of a supplied passage.
- Verification of returned "quote" strings against the supplied passages.
- Automatic repair loop: if verification fails, call llm_edit_recipe asking the model to fix unsupported citations.
- Deterministic model settings encouraged (temperature=0 by default when using HTTP).
- Backwards-compatible CLI flags to control retrieval, verification, retries, top-k, and ToT behavior.

Usage:
  python generate_recipe.py --src /path/video.mp4 --transcript transcript.txt --out recipe.json
  python generate_recipe.py --src ... --transcript ... --out ... --verify --top-k 6 --retry-fix 2

Requires:
- Ollama CLI in PATH or Ollama HTTP daemon reachable (set OLLAMA_HOST).
- Optionally tot_prompt_patch.py alongside this file for a nicer generic ToT helper.

If you use this with the GUI, import generate_recipe_from_transcript and llm_edit_recipe
and run them in a background thread (the functions are safe to call in-process).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter, OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# Try to import tot helper (optional)
try:
    from tot_prompt_patch import get_tot_prompt
except Exception:
    def get_tot_prompt(tot_text: Optional[str] = None, include_default_if_empty: bool = True) -> str:
        GENERIC = (
            "🧠 Generic ToT — clip selection & recipe assembly\n"
            "1) Segment: break transcript into logical parts (hook, setup, demo, conclusion).\n"
            "2) Select 3–5 clips, target 25–60s each; prioritize hooks, demonstrations, safety, CTA.\n"
            "3) Provide concise labels, overlay text (top), captions (bottom), and subtitles with timestamps.\n"
            "4) Return a single JSON recipe object with top-level keys: src, style_profile, caption_style, highlight_style, platforms, multi_platform, clips.\n"
            "Follow the ToT exactly when deciding clips."
        )
        if tot_text and tot_text.strip():
            return "Follow this ToT exactly when deciding what clips to create:\n\n" + tot_text.strip()
        return "Follow this ToT exactly when deciding what clips to create:\n\n" + GENERIC if include_default_if_empty else ""

# Optional HTTP client for Ollama
try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

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
# Transcript grouping loader (as before)
# -------------------------
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
            items.append({"start": ts, "text": remainder})
            i += 1
            continue
        if ts is not None and not remainder:
            j = i + 1
            buf = []
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                nxt_first = nxt.split()[0] if nxt.split() else ""
                if parse_time_to_seconds(nxt_first) is not None:
                    break
                buf.append(nxt)
                j += 1
            items.append({"start": ts, "text": " ".join(buf).strip()})
            i = j
            continue
        items.append({"start": None, "text": ln})
        i += 1
    return items


# -------------------------
# Passage chunking & retrieval
# -------------------------
def chunk_transcript_into_passages(transcript_text: str, chunk_seconds: int = 30) -> List[Dict[str, Any]]:
    """
    Chunk transcript into passages ~chunk_seconds long using timestamped lines if present.
    Returns list of passages: { doc_id, start (HH:MM:SS), end (HH:MM:SS), text }
    """
    lines = [ln.strip() for ln in transcript_text.splitlines() if ln.strip()]
    passages: List[Dict[str, Any]] = []
    cur_text: List[str] = []
    cur_start: Optional[float] = None
    cur_end: Optional[float] = None
    idx = 0
    for ln in lines:
        m = re.match(r"^(\d{1,2}:\d{2}:\d{2})([.,]\d{3})?\s+(.*)$", ln)
        if m:
            ts = m.group(1)
            body = m.group(3)
            sec = sum(int(x) * factor for x, factor in zip(ts.split(":"), [3600, 60, 1]))
            if cur_start is None:
                cur_start = sec
            cur_end = sec
            cur_text.append(f"{ts} {body}")
        else:
            if cur_start is None:
                cur_start = 0.0
            cur_text.append(ln)
        if cur_start is not None and cur_end is not None and (cur_end - cur_start) >= chunk_seconds:
            idx += 1
            passages.append({
                "doc_id": f"p{idx:04d}",
                "start": seconds_to_hhmmss(cur_start),
                "end": seconds_to_hhmmss(cur_end),
                "text": "\n".join(cur_text)
            })
            cur_text = []
            cur_start = None
            cur_end = None
    if cur_text:
        idx += 1
        cur_start_val = cur_start if cur_start is not None else 0.0
        cur_end_val = cur_end if cur_end is not None else (cur_start_val + chunk_seconds)
        passages.append({
            "doc_id": f"p{idx:04d}",
            "start": seconds_to_hhmmss(cur_start_val),
            "end": seconds_to_hhmmss(cur_end_val),
            "text": "\n".join(cur_text)
        })
    return passages


def simple_retrieve(passages: List[Dict[str, Any]], query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Naive token-overlap retrieval. Replace with vector search for production.
    """
    q_tokens = re.findall(r"\w+", query.lower())
    qc = Counter(q_tokens)
    scores: List[Tuple[int, Dict[str, Any]]] = []
    for p in passages:
        p_tokens = re.findall(r"\w+", p["text"].lower())
        score = sum(min(qc[t], p_tokens.count(t)) for t in qc)
        scores.append((score, p))
    scores.sort(key=lambda x: x[0], reverse=True)
    results = [p for s, p in scores[:top_k] if s > 0]
    # if no positive scores, return the first top_k passages as fallback
    if not results:
        return passages[:top_k]
    return results


def passages_to_prompt_block(passages: List[Dict[str, Any]]) -> str:
    blocks = []
    for p in passages:
        blocks.append(f"====DOC id={p['doc_id']} start={p['start']} end={p['end']}====\n{p['text']}")
    return "\n\n".join(blocks)


# -------------------------
# Robust JSON extraction
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
def clamp_and_normalize_clip(clip: Dict[str, Any], video_duration: Optional[float], transcript_blocks: Optional[List[Dict[str, Any]]] = None, min_clip_len: float = 3.0) -> Dict[str, Any]:
    def to_seconds_field(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            return parse_time_to_seconds(v)
        return None

    s = to_seconds_field(clip.get("start"))
    e = to_seconds_field(clip.get("end"))
    dur = clip.get("duration_sec") or clip.get("duration")
    if s is None and e is None and dur is None:
        s = 0.0
        e = min_clip_len
    if s is None and e is not None and dur is not None:
        s = e - float(dur)
    if e is None and s is not None and dur is not None:
        e = s + float(dur)
    if s is None:
        s = 0.0
    if e is None:
        e = s + max(min_clip_len, float(dur or min_clip_len))

    if video_duration is not None:
        max_end = max(0.0, video_duration - SAFETY_MARGIN)
        if e > max_end:
            e = max_end
        if s >= e:
            s = max(0.0, e - max(min_clip_len, float(dur or min_clip_len)))

    if (e - s) < min_clip_len:
        e = s + min_clip_len

    clip["start"] = seconds_to_hhmmss(s)
    clip["end"] = seconds_to_hhmmss(e)
    clip["duration_sec"] = int(round(max(0.0, e - s)))

    subs = clip.get("subtitles") or []
    if not subs and transcript_blocks:
        subs = build_subtitles_from_transcript_blocks(transcript_blocks, s, e)
    if not subs:
        subs = [{"from": seconds_to_hhmmss_ms(s), "to": seconds_to_hhmmss_ms(min(e, s + 2.0)), "text": ""}]
    normalized_subs = []
    for sub in subs:
        sf = to_seconds_field(sub.get("from") or sub.get("start"))
        ef = to_seconds_field(sub.get("to") or sub.get("end"))
        txt = sub.get("text") or ""
        if sf is None and ef is None:
            continue
        if sf is None:
            sf = max(s, ef - 4.0)
        if ef is None:
            ef = min(e, sf + 4.0)
        if sf < s:
            sf = s
        if ef > e:
            ef = e
        if ef <= sf:
            ef = min(e, sf + 0.5)
            if ef <= sf:
                continue
        normalized_subs.append({"from": seconds_to_hhmmss_ms(sf), "to": seconds_to_hhmmss_ms(ef), "text": " ".join(str(txt).split())})
    clip["subtitles"] = normalized_subs if normalized_subs else [{"from": seconds_to_hhmmss_ms(s), "to": seconds_to_hhmmss_ms(min(e, s + 2.0)), "text": ""}]
    return clip


# -------------------------
# Build subtitles from transcript (reused)
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
# Ollama call (HTTP preferred if configured)
# -------------------------
def call_ollama_raw(prompt: str, model: str = "llama2", use_http_if_possible: bool = True, timeout: int = 60, temperature: float = 0.0) -> str:
    try_http = False
    if use_http_if_possible and requests is not None:
        try_http_env = os.environ.get("OLLAMA_USE_HTTP", "").strip() == "1"
        if try_http_env or os.environ.get("OLLAMA_HOST"):
            try_http = True
    if try_http and requests is not None:
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        url = host.rstrip("/") + "/api/generate"
        payload = {"model": model, "prompt": prompt, "maxTokens": 2000}
        # Some Ollama HTTP deployments accept additional inference settings in the payload
        # Attempt to add "temperature" if the server supports it.
        payload["temperature"] = float(temperature)
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.text
    # fallback to CLI
    try:
        proc = subprocess.run(["ollama", "run", model, prompt], capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return out
    except FileNotFoundError as ex:
        raise RuntimeError("Ollama CLI not found and HTTP not configured/available.") from ex


# -------------------------
# LLM edit (post-generation)
# -------------------------
def llm_edit_recipe(recipe: Dict[str, Any],
                    instruction: str,
                    model: str = "llama2",
                    tot_text: Optional[str] = None,
                    include_default_tot: bool = True,
                    use_http_if_possible: bool = True,
                    video_duration: Optional[float] = None,
                    transcript_blocks: Optional[List[Dict[str, Any]]] = None,
                    max_tokens: int = 2000,
                    verbose: bool = False) -> Dict[str, Any]:
    if not instruction or not instruction.strip():
        raise ValueError("No edit instruction provided.")
    tot_block = get_tot_prompt(tot_text, include_default_if_empty=include_default_tot)
    system = (
        (tot_block + "\n\n") if tot_block else ""
    ) + (
        "You are Video Ops Mentor. RETURN ONLY a single JSON object (no surrounding text). "
        "The JSON must preserve required keys: src, clips, caption_style, highlight_style, platforms, multi_platform. "
        "Each clip must include start (HH:MM:SS), end (HH:MM:SS), duration_sec (int), and subtitles array where each subtitle has from (HH:MM:SS,mmm), to (HH:MM:SS,mmm), and text."
    )
    prompt = system + "\n\nINPUT_RECIPE:\n" + json.dumps(recipe, ensure_ascii=False, indent=2) + "\n\nINSTRUCTION:\n" + instruction + "\n\nReturn the updated full JSON recipe only."
    raw = call_ollama_raw(prompt, model=model, use_http_if_possible=use_http_if_possible, timeout=120, temperature=0.0)
    parsed = try_parse_json_from_model_output(raw)
    if not isinstance(parsed, dict) or "clips" not in parsed or not isinstance(parsed["clips"], list):
        raise ValueError("Edited recipe missing valid 'clips' list.")
    parsed["src"] = recipe.get("src", parsed.get("src"))
    new_clips = []
    for c in parsed.get("clips", []):
        try:
            new_clips.append(clamp_and_normalize_clip(c, video_duration, transcript_blocks))
        except Exception:
            continue
    if not new_clips:
        raise ValueError("No valid clips after normalization in edited recipe.")
    parsed["clips"] = new_clips
    for k in ("caption_style", "highlight_style", "platforms", "multi_platform", "style_profile", "generate_thumbnails", "add_text_overlay"):
        if k not in parsed and k in recipe:
            parsed[k] = recipe[k]
    return parsed


# -------------------------
# Citation verification
# -------------------------
def verify_recipe_citations(recipe: Dict[str, Any], passages_index: Dict[str, str]) -> Tuple[bool, List[str]]:
    """
    Check that each 'quote' in recipe["clips"][*]["sources"] is an exact substring
    of the corresponding passages_index[doc_id]. If a quote is missing, replace it with "".
    Returns (is_valid, errors). is_valid == True only if all quotes matched.
    """
    errors: List[str] = []
    valid = True
    clips = recipe.get("clips", [])
    for ci, clip in enumerate(clips, start=1):
        srcs = clip.get("sources", []) or []
        new_srcs = []
        for s in srcs:
            doc = s.get("doc_id")
            quote = s.get("quote", "") or ""
            if not doc:
                errors.append(f"clip[{ci}] missing doc_id in source entry: {s}")
                valid = False
                new_srcs.append(s)
                continue
            if doc not in passages_index:
                errors.append(f"clip[{ci}] references unknown doc_id {doc}")
                valid = False
                new_srcs.append(s)
                continue
            passage_text = passages_index[doc]
            if quote:
                if quote not in passage_text:
                    errors.append(f"clip[{ci}] quote not found in {doc}: '{quote[:120]}...'")
                    # fix by clearing quote and marking invalid
                    s["quote"] = ""
                    valid = False
            new_srcs.append(s)
        clip["sources"] = new_srcs
    return valid, errors


# -------------------------
# High-level generation (retrieval + prompt assembly + verification + optional repair)
# -------------------------
def generate_recipe_from_transcript(src: str,
                                   transcript_path: str,
                                   model: str = "llama2",
                                   tot_text: Optional[str] = None,
                                   include_default_tot: bool = True,
                                   use_http_if_possible: bool = True,
                                   top_k: int = 6,
                                   chunk_seconds: int = 30,
                                   verify: bool = True,
                                   retry_fix: int = 1,
                                   max_clips: int = 4,
                                   min_duration: int = 25,
                                   max_duration: int = 60,
                                   verbose: bool = False) -> Dict[str, Any]:
    """
    Main flow:
      1. Read transcript and chunk into passages.
      2. Retrieve top_k passages relevant to the transcript / clip task (naive retrieval).
      3. Build strict prompt including only the retrieved passages and ToT contract.
      4. Call LLM to generate recipe JSON.
      5. Parse JSON, normalize clips.
      6. If verify=True, verify citation quotes against supplied passages; if verification fails and retry_fix>0,
         call llm_edit_recipe asking the model to fix unsupported citations and repeat verification.
    """
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Source video not found: {src}")
    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as fh:
        transcript_text = fh.read()

    transcript_blocks = load_transcript_grouped(transcript_path)
    passages = chunk_transcript_into_passages(transcript_text, chunk_seconds=chunk_seconds)
    # Build a short query to retrieve passages: use a few keywords from the transcript header or user-provided tot_text
    # For simplicity, derive query from the first 2000 chars of transcript
    short_preview = transcript_text[:2000]
    # choose a simple query: top nouns/words from preview (naive)
    q_tokens = re.findall(r"\w+", short_preview.lower())
    query = " ".join(q_tokens[:200])  # naive
    top_passages = simple_retrieve(passages, query, top_k=top_k)
    passages_block = passages_to_prompt_block(top_passages)
    # Build mapping for verification
    passages_index = {p["doc_id"]: p["text"] for p in top_passages}

    tot_block = get_tot_prompt(tot_text, include_default_if_empty=include_default_tot)

    system_contract = (
        "CONTRACT: You MUST only use the PASSAGES provided in the prompt below. Do NOT use any external knowledge. "
        "Return ONLY a single JSON object (no explanations). If a required fact is not present in the passages, set the field to an empty value or sources: [].\n\n"
        "When you include any factual claim (clip start/end, overlay text taken from transcript, quoted evidence), each clip must include a 'sources' array with entries of the form: "
        '{"doc_id":"<id>","start":"<HH:MM:SS>","end":"<HH:MM:SS>","quote":"<exact excerpt from that passage>"} . '
        "The 'quote' MUST be an exact substring of the corresponding passage text provided. If you cannot find support, set 'quote' to empty and/or set sources: []."
    )

    system = (tot_block + "\n\n" if tot_block else "") + system_contract

    user_task = (
        "PASSAGES:\n\n" + passages_block + "\n\n"
        "TASK:\n"
        f"Produce a JSON recipe object for converting the source video into short clips. Required top-level keys: src, style_profile, generate_thumbnails, add_text_overlay, multi_platform, platforms, caption_style, highlight_style, clips.\n"
        "Each clip must include: id, label, start (HH:MM:SS), end (HH:MM:SS), duration_sec (int), subtitles (array), overlay_text (optional), sources (array as specified above). "
        f"Prefer producing between 3 and {max_clips} clips, each between {min_duration} and {max_duration} seconds. Ensure duration_sec matches end-start. Add thumbnail metadata for each clip.\n"
        "Return the JSON recipe only."
    )

    prompt = system + "\n\n" + user_task

    if verbose:
        print("[DEBUG] Prompt length:", len(prompt), file=sys.stderr)
        print("[DEBUG] Sending prompt to model...", file=sys.stderr)

    raw = call_ollama_raw(prompt, model=model, use_http_if_possible=use_http_if_possible, timeout=120, temperature=0.0)

    if verbose:
        print("[DEBUG] Raw model output head:", raw[:300], file=sys.stderr)

    parsed = try_parse_json_from_model_output(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Model did not return a JSON object.")

    # Ensure clips list exists; fallback if not
    if "clips" not in parsed or not isinstance(parsed["clips"], list):
        if verbose:
            print("[WARN] Model output missing clips; building fallback recipe.", file=sys.stderr)
        parsed = build_fallback_recipe(src, transcript_blocks)
    else:
        # normalize clips
        norm_clips = []
        for c in parsed.get("clips", []):
            try:
                norm_clips.append(clamp_and_normalize_clip(c, video_duration=None, transcript_blocks=transcript_blocks, min_clip_len=min_duration))
            except Exception:
                continue
        if not norm_clips:
            parsed = build_fallback_recipe(src, transcript_blocks)
        else:
            parsed["clips"] = norm_clips

    parsed["src"] = os.path.abspath(src)

    # Verification + repair loop
    if verify:
        is_valid, errors = verify_recipe_citations(parsed, passages_index)
        if verbose:
            if is_valid:
                print("[DEBUG] All citation quotes verified successfully.", file=sys.stderr)
            else:
                print("[WARN] Citation verification failed:", file=sys.stderr)
                for e in errors:
                    print(" -", e, file=sys.stderr)

        tries = 0
        while (not is_valid) and tries < retry_fix:
            tries += 1
            if verbose:
                print(f"[DEBUG] Attempting repair pass {tries}/{retry_fix} via llm_edit_recipe...", file=sys.stderr)
            # craft an instruction that asks the model to fix only citations that aren't present
            instruct = (
                "Fix the recipe so that every 'sources' entry contains a 'quote' "
                "that is an exact substring of one of the supplied PASSAGES. "
                "If a claim cannot be supported by the supplied passages, set its sources to []. "
                "Do NOT invent any new passages or facts. Preserve recipe['src'] and top-level keys. Return JSON only."
            )
            try:
                repaired = llm_edit_recipe(parsed, instruct, model=model, tot_text=tot_text, include_default_tot=include_default_tot, use_http_if_possible=use_http_if_possible, video_duration=None, transcript_blocks=transcript_blocks, verbose=verbose)
                # verify again
                is_valid, errors = verify_recipe_citations(repaired, passages_index)
                parsed = repaired
                if verbose:
                    if is_valid:
                        print("[DEBUG] Repair succeeded and citations now verify.", file=sys.stderr)
                    else:
                        print("[WARN] Repair did not fix all citations:", file=sys.stderr)
                        for e in errors:
                            print(" -", e, file=sys.stderr)
            except Exception as e:
                if verbose:
                    print("[ERROR] Repair attempt failed:", e, file=sys.stderr)
                break

    return parsed


# -------------------------
# Fallback recipe builder (simple)
# -------------------------
def build_fallback_recipe(src_path: str, transcript_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    start = 0.0
    end = 40.0
    for b in transcript_blocks:
        if b.get("start") is not None:
            start = float(b["start"])
            end = start + 45.0
            break
    clip = OrderedDict([
        ("id", "01"),
        ("label", "Key Moment"),
        ("start", seconds_to_hhmmss(start)),
        ("end", seconds_to_hhmmss(end)),
        ("duration_sec", int(round(end - start))),
        ("overlay_text", [{"text": "Key Moment", "placement": "top_center"}]),
        ("subtitles", build_subtitles_from_transcript_blocks(transcript_blocks, start, end) or [{"from": seconds_to_hhmmss_ms(start), "to": seconds_to_hhmmss_ms(min(end, start+2.0)), "text": ""}]),
        ("sources", [])
    ])
    recipe = OrderedDict([
        ("src", os.path.abspath(src_path)),
        ("style_profile", "educational"),
        ("generate_thumbnails", False),
        ("add_text_overlay", True),
        ("multi_platform", True),
        ("platforms", ["vertical", "square", "landscape"]),
        ("caption_style", {"placement": "bottom_center", "font": "Roboto", "size": "small"}),
        ("highlight_style", {"placement": "top_center", "font": "Open Sans", "size": "medium"}),
        ("clips", [clip])
    ])
    return recipe


# -------------------------
# CLI entrypoint
# -------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate recipe JSON from transcript using local Ollama model (retrieval-grounded).")
    parser.add_argument("--src", required=True, help="Path to source video file")
    parser.add_argument("--transcript", required=True, help="Path to transcript file (.txt or .srt)")
    parser.add_argument("--out", required=True, help="Output recipe JSON path")
    parser.add_argument("--model", default="llama2", help="Ollama model name")
    parser.add_argument("--tot", dest="tot_text", help="Optional ToT text to override generic ToT")
    parser.add_argument("--use-default-tot", action="store_true", help="Ensure built-in generic ToT is included (default)")
    parser.add_argument("--no-default-tot", action="store_true", help="Disable inclusion of built-in generic ToT")
    parser.add_argument("--top-k", type=int, default=6, help="Number of retrieved passages to include in prompt")
    parser.add_argument("--chunk-seconds", type=int, default=30, help="Approx passage chunk size in seconds")
    parser.add_argument("--verify", action="store_true", help="Verify quoted citations against supplied passages and optionally attempt repairs")
    parser.add_argument("--retry-fix", type=int, default=1, help="Number of repair attempts if verification fails")
    parser.add_argument("--max-clips", type=int, default=4)
    parser.add_argument("--min-duration", type=int, default=25)
    parser.add_argument("--max-duration", type=int, default=60)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    include_default = not bool(args.no_default_tot)
    if args.use_default_tot:
        include_default = True

    try:
        recipe = generate_recipe_from_transcript(
            src=args.src,
            transcript_path=args.transcript,
            model=args.model,
            tot_text=args.tot_text,
            include_default_tot=include_default,
            use_http_if_possible=True,
            top_k=args.top_k,
            chunk_seconds=args.chunk_seconds,
            verify=bool(args.verify),
            retry_fix=int(args.retry_fix),
            max_clips=args.max_clips,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            verbose=args.verbose
        )
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}", file=sys.stderr)
        return 2

    try:
        raw = json.dumps(recipe, ensure_ascii=False, indent=2)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(raw)
        print(f"[INFO] Recipe written to {args.out}")
    except Exception as e:
        print(f"[ERROR] Failed to write recipe: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())