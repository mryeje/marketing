"""
tot_prompt_patch.py

Generic ToT (Theory of Task) helper for generate_recipe_ollama.py and the GUI.

This module provides a generic, domain-agnostic ToT template and a helper
to return a ToT block to prepend to LLM system prompts. The ToT is intentionally
generic so it can be reused across different videos/transcripts.

Usage:
    from tot_prompt_patch import get_tot_prompt
    tot_block = get_tot_prompt(tot_text=args.tot, include_default_if_empty=True)
    system_instructions = tot_block + "\n\n" + base_system
"""
from typing import Optional

GENERIC_DEFAULT_TOT = """🧠 Generic ToT (Theory of Task) — clip selection & recipe assembly
1) Segmenting: Break the transcript into clear, logical segments (intro/hook,
   setup, demonstrations/steps, conclusion/CTA). Use timestamps in the transcript
   where available to place segment boundaries.
2) Priorities for clip selection:
   - Select 3–5 clips per source that best represent the video's narrative and
     viewer value.
   - Clip lengths: target 25–60 seconds each (adjust to context; keep hooks shorter).
   - Prioritize: Hooks (engagement), action/demonstration, key takeaways, safety/caveats, CTA.
3) Clip labeling: Provide concise, human-readable labels for each clip (one line).
4) Overlays & captions:
   - Put highlights/overlay text near the top of frame; captions at the bottom.
   - Place an attention-grabbing overlay in the first 1–3 seconds for hook clips.
   - Ensure captions are short, actionable, and readable for silent viewing.
5) Subtitles & timing:
   - Use transcript timestamps when available; otherwise create conservative subtitle
     time windows that match on-screen speech.
   - Provide subtitles as objects with from (HH:MM:SS,mmm), to (HH:MM:SS,mmm), text.
6) Output schema and constraints:
   - Return a single JSON recipe object preserving required top-level keys: src, style_profile,
     caption_style, highlight_style, platforms, multi_platform, clips.
   - Each clip must include id, label, start (HH:MM:SS), end (HH:MM:SS), duration_sec (int),
     subtitles (array), and optional overlay_text and thumbnail metadata.
   - Do not change file paths or invent unrelated top-level keys.
7) If asked to refine, perform edits on the recipe JSON only and return a JSON-only response.
"""

def get_tot_prompt(tot_text: Optional[str] = None, include_default_if_empty: bool = True) -> str:
    """
    Return a ToT text block to prepend to the LLM system prompt.

    - tot_text: optional user-provided ToT string; if provided it will be used.
    - include_default_if_empty: if True and tot_text is falsy, return GENERIC_DEFAULT_TOT.

    Returns a string that begins with a short directive and the ToT content.
    """
    if tot_text and tot_text.strip():
        return "Follow this ToT exactly when deciding what clips to create:\n\n" + tot_text.strip()
    if include_default_if_empty:
        return "Follow this ToT exactly when deciding what clips to create:\n\n" + GENERIC_DEFAULT_TOT
    return ""