#!/usr/bin/env python3
"""
Adapter for l2s_core.py to be used by main.py.

Provides:
 - process_recipe_in_jobdir(recipe_dict, job_dir, args=None)
     Writes recipe.json into job_dir (if not already present), normalizes local file:// URIs,
     constructs a minimal args namespace and calls l2s_core.process_recipe(recipe_path, args).
     Returns the dict result from l2s_core.

 - CLI mode:
     * If a path arg is provided, treats it as the path to a recipe JSON and processes it in-place
       (job_dir = dirname(recipe_path)).
     * Otherwise reads recipe JSON from stdin, creates a temporary job dir and processes it.
     Writes the result JSON to stdout on success; on error writes traceback to stderr and exits nonzero.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import traceback
import urllib.parse
from types import SimpleNamespace
from typing import Optional, Any, Dict

# Try to import the core module; store import error for helpful messages.
try:
    import l2s_core as core  # type: ignore
    _CORE_IMPORT_ERR = None
except Exception as e:
    core = None
    _CORE_IMPORT_ERR = e

def _normalize_file_uri_to_path(p: Optional[str]) -> Optional[str]:
    """
    Convert file:// URI into a local filesystem path (Windows-aware).
    Leaves non-file URIs untouched.
    """
    if not p or not isinstance(p, str):
        return p
    p = p.strip()
    if p.startswith("file://"):
        path = urllib.parse.unquote(p[len("file://"):])
        # On Windows file URIs often start with /C:/... so strip leading slash
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return path
    return p

def _make_default_args() -> SimpleNamespace:
    """
    Construct a minimal args-like object with attributes process_recipe expects.
    Extend if your usage requires more attributes (zoom, device, model path, etc.).
    """
    if core is not None:
        return SimpleNamespace(
            device="auto",
            model=getattr(core, "DEFAULT_MODEL_PATH", "yolov8n-pose.pt"),
            confidence=0.25,
            prefer_pillow=True,
            zoom=getattr(core, "ZOOM", 1.05),
            ybias=getattr(core, "Y_BIAS", 0.10),
            TARGET_W=getattr(core, "TARGET_W", 1080),
            TARGET_H=getattr(core, "TARGET_H", 1920),
        )
    else:
        return SimpleNamespace(
            device="auto",
            model="yolov8n-pose.pt",
            confidence=0.25,
            prefer_pillow=True,
            zoom=1.05,
            ybias=0.10,
            TARGET_W=1080,
            TARGET_H=1920,
        )

def process_recipe_in_jobdir(recipe_dict: Dict[str, Any], job_dir: str, args: Optional[SimpleNamespace] = None) -> Dict[str, Any]:
    """
    Write recipe_dict to job_dir/recipe.json (if not present) and call l2s_core.process_recipe(recipe_path, args).
    Returns the dict result from l2s_core.

    - If a recipe.json already exists in job_dir, it will be used (adapter will not overwrite it).
    - Recipe dict top-level "src" file:// URIs are normalized to local paths before writing.
    - Does NOT remove the recipe file after processing so l2s_core outputs colocate with it.
    """
    if core is None:
        raise RuntimeError(f"Could not import l2s_core: {_CORE_IMPORT_ERR}")

    if args is None:
        args = _make_default_args()

    os.makedirs(job_dir, exist_ok=True)
    recipe_path = os.path.join(job_dir, "recipe.json")

    # If recipe.json already exists in job_dir, prefer it and do not overwrite.
    if not os.path.isfile(recipe_path):
        # Normalize known common URI to local paths before writing
        rd = dict(recipe_dict) if isinstance(recipe_dict, dict) else recipe_dict
        try:
            if isinstance(rd.get("src"), str):
                rd["src"] = _normalize_file_uri_to_path(rd["src"])
        except Exception:
            # non-fatal; proceed with original value
            pass
        with open(recipe_path, "w", encoding="utf-8") as f:
            json.dump(rd, f, ensure_ascii=False, indent=2)

    # Call the core pipeline with the recipe path and args.
    try:
        # process_recipe signature: (recipe_path: str, args)
        result = core.process_recipe(recipe_path, args)
        # Ensure result is a dict (core returns a dict on success)
        if not isinstance(result, dict):
            return {"result": result}
        return result
    except Exception as exc:
        tb = traceback.format_exc()
        raise RuntimeError(f"l2s_core.process_recipe failed: {exc}\n{tb}") from exc

def cli_main():
    """
    CLI wrapper:
      - If first argv is a path to a recipe JSON file, process it in-place (job_dir = dirname(recipe_path)).
      - Otherwise read recipe JSON from stdin and create a temporary job dir for processing.
    On success: write result JSON to stdout and exit 0.
    On failure: write traceback to stderr and exit non-zero.
    """
    if core is None:
        print(f"[ERROR] Could not import l2s_core: {_CORE_IMPORT_ERR}", file=sys.stderr)
        sys.exit(2)

    try:
        if len(sys.argv) > 1:
            # treat arg as recipe path
            recipe_path = sys.argv[1]
            with open(recipe_path, "r", encoding="utf-8") as f:
                recipe = json.load(f)
            job_dir = os.path.dirname(os.path.abspath(recipe_path)) or os.getcwd()
        else:
            raw = sys.stdin.read()
            if not raw:
                print("[ERROR] No input provided on stdin and no recipe file path arg supplied.", file=sys.stderr)
                sys.exit(3)
            recipe = json.loads(raw)
            job_dir = tempfile.mkdtemp(prefix="l2s_job_")
    except Exception as e:
        print(f"[ERROR] Failed to read recipe JSON: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(4)

    try:
        args = _make_default_args()
        result = process_recipe_in_jobdir(recipe, job_dir, args=args)
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.flush()
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Processing failed: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(5)

if __name__ == "__main__":
    cli_main()