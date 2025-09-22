"""
Regenerated main.py for Long2Short service.

This FastAPI app exposes a /process endpoint that accepts a recipe JSON,
creates a timestamped job directory, writes the recipe, invokes the adapter
(either in-process if available or as a subprocess), captures adapter logs,
and attaches overlay queue metadata (path, size, entries_count) to the response.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# local helper to attach overlay queue metadata
from overlays_helper import _find_and_attach_overlay_queue_metadata

# basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("long2short")

app = FastAPI(title="Long2Short")

# Default downloads base (matches the style seen in your logs); can be overridden by env var.
DEFAULT_DOWNLOADS_DIR = Path(os.getenv("L2S_DOWNLOADS_DIR", Path.cwd() / "Downloads"))


class ProcessResponse(BaseModel):
    job_id: str
    job_dir: str
    adapter_result: Optional[Dict[str, Any]] = None
    overlay_queue: Optional[Dict[str, Any]] = None
    adapter_exit_code: Optional[int] = None
    adapter_stdout_tail: Optional[str] = None
    adapter_stderr_tail: Optional[str] = None


@app.post("/process", response_model=ProcessResponse)
async def process_endpoint(request: Request):
    """
    Accepts a recipe JSON body and processes it. Returns a summary including the
    job directory and overlay queue metadata (if present).
    """
    try:
        recipe = await request.json()
    except Exception as exc:
        logger.exception("Failed to parse incoming JSON")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    job_id = str(uuid.uuid4())
    # Use date-prefixed folder to aid debugging if desired
    job_dir = DEFAULT_DOWNLOADS_DIR / job_id
    try:
        job_dir.mkdir(parents=True, exist_ok=False)
    except Exception:
        # if folder exists or cannot be created, still continue with unique path
        job_dir = DEFAULT_DOWNLOADS_DIR / f"{job_id}-{int(datetime.utcnow().timestamp())}"
        job_dir.mkdir(parents=True, exist_ok=True)

    recipe_path = job_dir / "recipe.json"
    try:
        with recipe_path.open("w", encoding="utf-8") as fh:
            json.dump(recipe, fh, indent=2)
    except Exception as exc:
        logger.exception("Failed to write recipe to job_dir")
        raise HTTPException(status_code=500, detail=f"Failed to write recipe: {exc}")

    logger.info("Job %s: starting, job_dir=%s", job_id, str(job_dir))

    adapter_result = None
    adapter_exit_code = None
    stdout_tail = None
    stderr_tail = None

    try:
        adapter_result, adapter_exit_code, stdout_tail, stderr_tail = _call_adapter(recipe, recipe_path, job_dir, job_id)
    except Exception as exc:
        # Log the error, but still return the job_dir and any overlay queue metadata we can find.
        logger.exception("Job %s: unexpected exception while running adapter", job_id)
        # continue to return overlay_queue info; surface adapter details in response
        adapter_result = {"error": str(exc)}

    # Build response
    result: Dict[str, Any] = {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "adapter_result": adapter_result,
        "adapter_exit_code": adapter_exit_code,
        "adapter_stdout_tail": stdout_tail,
        "adapter_stderr_tail": stderr_tail,
    }

    # Attach overlay queue metadata (safe, non-blocking)
    try:
        result.update(_find_and_attach_overlay_queue_metadata(str(job_dir), include_content=False))
    except Exception:
        # be defensive: don't fail the response if helper has issues
        logger.exception("Failed to attach overlay queue metadata")

    return result


def _call_adapter(recipe_dict: Dict[str, Any], recipe_path: Path, job_dir: Path, job_id: str):
    """
    Try multiple ways to run the adapter (in this order):
      1) import adapter module and call adapter.process_recipe(recipe_dict, job_dir, job_id)
      2) import process_recipe module and call process_recipe.process_recipe(...)
      3) run a local 'adapter.py' or 'process_recipe.py' as a subprocess

    Captures stdout/stderr into job_dir logs and returns a tuple:
      (adapter_result_dict_or_text, exit_code_or_none, stdout_tail, stderr_tail)

    Raises RuntimeError if subprocess failed and returned no meaningful result.
    """
    project_root = Path(__file__).resolve().parent
    adapter_stdout_log = job_dir / "adapter_stdout.log"
    adapter_stderr_log = job_dir / "adapter_stderr.log"

    # Try in-process adapter call if available (preferred for speed in debug)
    try:
        # Attempt import adapter
        import importlib

        for mod_name in ("adapter", "process_recipe"):
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                mod = None

            if mod:
                # prefer process_recipe/process_recipe or adapter.process_recipe
                func = None
                if hasattr(mod, "process_recipe"):
                    func = getattr(mod, "process_recipe")
                elif hasattr(mod, "main"):
                    func = getattr(mod, "main")
                if callable(func):
                    logger.info("Running adapter in-process via module %s", mod_name)
                    try:
                        # Many adapters accept (recipe_path, job_dir) or (recipe_dict, job_dir, job_id).
                        # Try common signatures defensively.
                        try:
                            res = func(str(recipe_path), str(job_dir))
                        except TypeError:
                            try:
                                res = func(recipe_dict, str(job_dir), job_id)
                            except TypeError:
                                res = func(recipe_dict, str(job_dir))
                        return res, 0, None, None
                    except Exception as exc:
                        # In-process adapter raised; capture and continue to subprocess fallback
                        logger.exception("In-process adapter call raised; falling back to subprocess")
                        # write exception to adapter_stderr.log
                        with adapter_stderr_log.open("w", encoding="utf-8") as f:
                            f.write("In-process adapter exception:\n")
                            f.write(str(exc))
                        # fall through to subprocess fallback
                        break
    except Exception:
        logger.exception("Unexpected error when attempting in-process adapter import")

    # Subprocess fallback - try known script names in project root
    candidates = [project_root / "adapter.py", project_root / "process_recipe.py", project_root / "main_adapter.py"]
    # also attempt to call a module via -m using 'process_recipe' or 'adapter'
    module_candidates = ["process_recipe", "adapter"]

    # Use subprocess.run and capture output to files
    def run_subprocess(cmd):
        logger.info("Running subprocess: %s", cmd)
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1800)
        except subprocess.TimeoutExpired as te:
            # write partial output if any
            with adapter_stdout_log.open("w", encoding="utf-8") as f:
                f.write(getattr(te, "stdout", "") or "")
            with adapter_stderr_log.open("w", encoding="utf-8") as f:
                f.write(getattr(te, "stderr", "") or "")
                f.write("\nProcess timed out\n")
            raise RuntimeError("Adapter subprocess timed out") from te

        # persist logs
        with adapter_stdout_log.open("w", encoding="utf-8") as f:
            f.write(proc.stdout or "")
        with adapter_stderr_log.open("w", encoding="utf-8") as f:
            f.write(proc.stderr or "")

        stdout_tail = "\n".join((proc.stdout or "").splitlines()[-200:])
        stderr_tail = "\n".join((proc.stderr or "").splitlines()[-200:])
        return proc.returncode, proc.stdout, proc.stderr, stdout_tail, stderr_tail

    # First try candidate scripts
    for script in candidates:
        if script.exists():
            cmd = [sys.executable, str(script), "--recipe", str(recipe_path), "--job-dir", str(job_dir)]
            try:
                code, out, err, out_tail, err_tail = run_subprocess(cmd)
                parsed = None
                # try to parse stdout as JSON (adapter may output JSON summary)
                try:
                    parsed = json.loads(out) if out else None
                except Exception:
                    parsed = out.strip() if out else None
                return parsed, code, out_tail, err_tail
            except Exception as exc:
                # if this candidate fails, move to next
                logger.exception("Subprocess script %s failed: %s", script, exc)

    # Next try running module via -m
    for mod in module_candidates:
        cmd = [sys.executable, "-m", mod, "--recipe", str(recipe_path), "--job-dir", str(job_dir)]
        try:
            code, out, err, out_tail, err_tail = run_subprocess(cmd)
            parsed = None
            try:
                parsed = json.loads(out) if out else None
            except Exception:
                parsed = out.strip() if out else None
            return parsed, code, out_tail, err_tail
        except Exception as exc:
            logger.exception("Subprocess -m %s failed: %s", mod, exc)

    # If we reach here, no adapter approach succeeded
    raise RuntimeError("Adapter subprocess failed or returned no result; see adapter_stdout.log and adapter_stderr.log in job_dir for details")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)