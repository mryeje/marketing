#!/usr/bin/env python3
"""
Adapter shim: process_recipe entrypoint.

- Supports CLI: python -m process_recipe --recipe <path> --job-dir <dir>
- Exposes process_recipe(...) for in-process calls with these accepted signatures:
    process_recipe(recipe_path: str, job_dir: str)
    process_recipe(recipe_dict: dict, job_dir: str, job_id: Optional[str])
Returns a dict summary and writes overlays_queue_*.json into job_dir.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def make_entries_from_recipe(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    src = recipe.get("src")
    clips = recipe.get("clips", [])
    multi = recipe.get("multi_platform", False)
    platforms = recipe.get("platforms", ["landscape"]) if multi else ["landscape"]
    style = recipe.get("style_profile")

    for clip in clips:
        clip_id = clip.get("id") or str(uuid.uuid4())[:8]
        start = clip.get("start")
        end = clip.get("end")
        label = clip.get("label")
        for plat in platforms:
            out_name = f"{clip_id}_{plat}.mp4"
            entry = {
                "id": f"{clip_id}-{plat}",
                "input_src": src,
                "clip": {"start": start, "end": end, "label": label, "id": clip_id},
                "platform": plat,
                "style_profile": style,
                "output_filename": out_name,
            }
            entries.append(entry)
    return entries


def write_overlays_queue(job_dir: Path, entries: List[Dict[str, Any]]) -> Path:
    queue = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "entries_count": len(entries),
        "entries": entries,
    }
    fname = job_dir / f"overlays_queue_{uuid.uuid4().hex}.json"
    with fname.open("w", encoding="utf-8") as fh:
        json.dump(queue, fh, indent=2)
    return fname


def process_recipe(
    recipe: Union[str, Dict[str, Any]],
    job_dir: str,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    In-process callable wrapper.

    Accepts either:
      - recipe: path to recipe.json (str), job_dir: path to write outputs (str)
      - recipe: recipe dict, job_dir: path to write outputs, optional job_id

    Returns a dict summary similar to the CLI JSON output.
    """
    # Normalize job_dir path
    job_path = Path(job_dir)
    job_path.mkdir(parents=True, exist_ok=True)

    # Load recipe if a path was passed
    if isinstance(recipe, str):
        recipe_path = Path(recipe)
        if not recipe_path.exists():
            return {"status": "error", "error": f"recipe not found: {recipe_path}"}
        with recipe_path.open("r", encoding="utf-8") as fh:
            recipe_dict = json.load(fh)
    else:
        recipe_dict = recipe

    # Build entries and write queue
    entries = make_entries_from_recipe(recipe_dict)
    queue_path = write_overlays_queue(job_path, entries)

    summary = {
        "status": "ok",
        "job_dir": str(job_path),
        "overlays_queue": str(queue_path),
        "entries_count": len(entries),
    }
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="process_recipe", description="Create overlays queue from recipe")
    parser.add_argument("--recipe", required=True, help="Path to recipe.json")
    parser.add_argument("--job-dir", required=True, help="Job directory to write outputs into")
    parser.add_argument("--print-queue", action="store_true", help="Also print the full queue JSON to stdout (careful if large)")
    args = parser.parse_args(argv)

    try:
        recipe_path = Path(args.recipe)
        job_dir = Path(args.job_dir)
        if not recipe_path.exists():
            print(json.dumps({"status": "error", "error": f"recipe not found: {recipe_path}"}))
            return 2
        job_dir.mkdir(parents=True, exist_ok=True)

        with recipe_path.open("r", encoding="utf-8") as fh:
            recipe = json.load(fh)

        entries = make_entries_from_recipe(recipe)
        queue_path = write_overlays_queue(job_dir, entries)

        summary = {
            "status": "ok",
            "job_dir": str(job_dir),
            "overlays_queue": str(queue_path),
            "entries_count": len(entries),
        }

        # Print a compact JSON summary for main.py to parse
        print(json.dumps(summary))

        # Optionally print the full overlays queue (useful for debugging)
        if args.print_queue:
            with queue_path.open("r", encoding="utf-8") as fh:
                sys.stdout.write("\n")
                sys.stdout.write(fh.read())

        return 0

    except Exception as exc:  # pragma: no cover - runtime safety
        err = {"status": "error", "error": str(exc)}
        print(json.dumps(err))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())