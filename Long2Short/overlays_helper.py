"""
Helper to find the latest overlays_queue_*.json in a job directory and return
small metadata suitable for attaching to an API response.

Drop this file next to your main.py (same package level) and use the helper
to attach overlay queue metadata into your /process response.
"""
import glob
import os
import json
from typing import Dict, Any

def _find_and_attach_overlay_queue_metadata(job_dir: str, include_content: bool = False, max_content_bytes: int = 100 * 1024) -> Dict[str, Any]:
    """
    Search job_dir for overlays_queue_*.json files, pick the newest one (by mtime),
    and return a small metadata dict suitable for attaching to an HTTP response.

    Returns shape:
      {"overlay_queue": None}
    or
      {"overlay_queue": {"path": "...", "size_bytes": 1234, "entries_count": 5, "content": {...} (optional)}}

    Notes:
      - include_content=False keeps response small (only path, size, entries_count).
      - include_content=True will include parsed JSON only when file size <= max_content_bytes.
      - This function is defensive and will not raise — it returns overlay_queue=None on failure.
    """
    out = {"overlay_queue": None}
    try:
        pattern = os.path.join(job_dir, "overlays_queue_*.json")
        files = glob.glob(pattern)
        if not files:
            return out

        latest = max(files, key=os.path.getmtime)
        meta = {"path": os.path.abspath(latest)}
        try:
            meta["size_bytes"] = os.path.getsize(latest)
        except Exception:
            meta["size_bytes"] = None

        payload = None
        try:
            with open(latest, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            entries = payload.get("entries", [])
            meta["entries_count"] = len(entries) if isinstance(entries, list) else None
        except Exception:
            meta["entries_count"] = None
            payload = None

        if include_content and payload is not None and meta.get("size_bytes") and meta["size_bytes"] <= max_content_bytes:
            meta["content"] = payload

        out["overlay_queue"] = meta
    except Exception:
        # Best-effort only — don't let metadata collection raise and disrupt main flow.
        try:
            out["overlay_queue_error"] = "failed to read overlay queue metadata"
        except Exception:
            pass
    return out