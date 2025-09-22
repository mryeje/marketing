from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Query
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import uuid
import os
import json
import logging
import traceback
from datetime import datetime
import subprocess
import sys
import urllib.parse


import glob



# Helper: attach overlay queue metadata for a completed job
def _find_and_attach_overlay_queue_metadata(job_dir, include_content=False, max_content_bytes=100*1024):
    """
    Search job_dir for overlays_queue_*.json files, pick the newest one (by mtime),
    and return a small metadata dict suitable for attaching to an HTTP response.
    Does NOT include full content by default (include_content=False). If included,
    content is only added when file size <= max_content_bytes to avoid huge responses.
    """
    out = {
        "overlay_queue": None
    }
    try:
        pattern = os.path.join(job_dir, "overlays_queue_*.json")
        files = glob.glob(pattern)
        if not files:
            return out

        # pick latest by modification time
        latest = max(files, key=os.path.getmtime)
        meta = {"path": os.path.abspath(latest)}
        try:
            size = os.path.getsize(latest)
            meta["size_bytes"] = size
        except Exception:
            meta["size_bytes"] = None

        # try to load JSON to determine entries_count (safe-read)
        try:
            with open(latest, "r", encoding="utf-8") as f:
                payload = json.load(f)
            entries = payload.get("entries", [])
            meta["entries_count"] = len(entries) if isinstance(entries, list) else None
        except Exception:
            meta["entries_count"] = None
            payload = None

        # optionally include content (only if small)
        if include_content and payload is not None and meta.get("size_bytes") and meta["size_bytes"] <= max_content_bytes:
            meta["content"] = payload
        # attach metadata
        out["overlay_queue"] = meta
    except Exception:
        # never crash the API for overlay metadata issues
        try:
            out["overlay_queue_error"] = "failed to read overlay queue metadata"
        except Exception:
            pass
    return out

# Example insertion point:
# After your job finishes and you build 'result' (the response body), do:
#
#    # result = { ... }  # existing response content built by your handler
#    result.update(_find_and_attach_overlay_queue_metadata(job_dir, include_content=False))
#
# Then return 'result' as the HTTP response.
#
# Notes:
# - include_content=False keeps the response small and only exposes the queue path and entries_count.
# - If you prefer the response to include full queue JSON when small, set include_content=True.
# - This helper is defensive and will not raise on failures (it returns overlay_queue=None or a small error field).


# Basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("long2short")

app = FastAPI(title="Long2Short Processor (with l2s_core)")

# In-memory jobs registry -- for production persist to disk or DB
JOBS: Dict[str, Dict[str, Any]] = {}

ROOT_DIR = Path.cwd()
JOB_RUN_DIR = ROOT_DIR / "job_runs"
JOB_RUN_DIR.mkdir(parents=True, exist_ok=True)
JOB_BASE_DIR = ROOT_DIR / "jobs"
JOB_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Try to import adapter; if not available we'll fallback to subprocess invocation of adapter CLI
try:
    import l2s_core_adapter as adapter  # type: ignore
    ADAPTER_AVAILABLE = True
except Exception:
    adapter = None
    ADAPTER_AVAILABLE = False

LS2_ADAPTER_CLI = str(Path(__file__).parent / "l2s_core_adapter.py")
LS2_CLI_PY = sys.executable if sys.executable else "python"

class Clip(BaseModel):
    id: str
    start: int
    end: int
    label: Optional[str] = None

class Recipe(BaseModel):
    src: str
    style_profile: Optional[str] = None
    generate_thumbnails: Optional[bool] = True
    add_text_overlay: Optional[bool] = False
    multi_platform: Optional[bool] = False
    platforms: Optional[List[str]] = None
    clips: Optional[List[Clip]] = None
    # allow arbitrary extra fields (overlay instructions etc.)
    class Config:
        extra = "allow"

def _append_job_log(job_id: str, text: str) -> None:
    try:
        p = JOB_RUN_DIR / f"{job_id}.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:
        logger.exception("Failed to write job log for %s", job_id)

def _normalize_file_uri_to_path(p: Optional[str]) -> Optional[str]:
    if not p or not isinstance(p, str):
        return p
    p = p.strip()
    if p.startswith("file://"):
        path = urllib.parse.unquote(p[len("file://"):])
        # On Windows file URIs commonly start with /C:/...
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return path
    return p

def _run_adapter_subprocess(recipe_dict: Dict[str, Any], job_dir: str, job_id: str, timeout: int = 60*60) -> Optional[Dict[str, Any]]:
    """
    Run l2s_core_adapter.py as a subprocess, passing recipe JSON on stdin.
    Expects adapter to write JSON to stdout. cwd and env are set to job_dir so l2s_core runs in the same folder
    as the source video if job_dir was chosen as the source parent directory.
    """
    cmd = [LS2_CLI_PY, LS2_ADAPTER_CLI]
    _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] FALLBACK_SUBPROCESS RUN: {' '.join(cmd)} job_dir={job_dir}")
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(recipe_dict).encode('utf-8'),
            capture_output=True,
            timeout=timeout,
            cwd=str(job_dir),
            env=os.environ.copy()
        )
        stdout = proc.stdout.decode(errors="ignore") if proc.stdout else ""
        stderr = proc.stderr.decode(errors="ignore") if proc.stderr else ""
        _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] SUBPROCESS rc={proc.returncode}")
        if stdout:
            _append_job_log(job_id, f"[SUBPROCESS STDOUT]\n{stdout}")
        if stderr:
            _append_job_log(job_id, f"[SUBPROCESS STDERR]\n{stderr}")
        if proc.returncode != 0:
            return None
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except Exception as e:
            _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] SUBPROCESS JSON PARSE ERROR: {e}")
            _append_job_log(job_id, stdout)
            return None
    except subprocess.TimeoutExpired as e:
        _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] SUBPROCESS TIMEOUT: {e}")
        return None
    except Exception as e:
        _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] SUBPROCESS EXCEPTION: {e}")
        return None

def _call_adapter(recipe_dict: Dict[str, Any], job_dir: str, job_id: str) -> Dict[str, Any]:
    """
    Try import-based call via adapter.process_recipe_in_jobdir first, fallback to subprocess CLI.
    Raises RuntimeError on failure.
    """
    # Prefer direct import call if adapter is available
    if ADAPTER_AVAILABLE and adapter is not None:
        try:
            _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] CALLING adapter.process_recipe_in_jobdir (import)")
            # adapter will write recipe.json into job_dir and call l2s_core there
            res = adapter.process_recipe_in_jobdir(recipe_dict, job_dir)
            return res
        except Exception as e:
            tb = traceback.format_exc()
            _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] IMPORT CALL ERROR: {e}")
            _append_job_log(job_id, tb)
            # fall through to subprocess fallback

    # Fallback to subprocess run of adapter CLI (adapter script must be present)
    if os.path.isfile(LS2_ADAPTER_CLI):
        _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] Falling back to adapter subprocess")
        res = _run_adapter_subprocess(recipe_dict, job_dir, job_id)
        if res is None:
            raise RuntimeError("Adapter subprocess failed or returned no result")
        return res

    raise RuntimeError("No adapter available to call l2s_core (import failed and adapter CLI missing)")

def _process_job(job_id: str, job_dir: Path) -> None:
    """
    Background worker: calls l2s_core via adapter, updates JOBS and writes logs.
    """
    start_ts = datetime.utcnow().isoformat() + "Z"
    _append_job_log(job_id, f"[{start_ts}] START job {job_id} job_dir={job_dir}")
    logger.info("Job %s: starting, job_dir=%s", job_id, job_dir)
    try:
        recipe_path = job_dir / "recipe.json"
        if not recipe_path.exists():
            msg = f"recipe file not found: {recipe_path}"
            _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] ERROR: {msg}")
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = {"message": msg}
            return
        with recipe_path.open("r", encoding="utf-8") as f:
            recipe_dict = json.load(f)

        # call adapter (import or subprocess)
        result = _call_adapter(recipe_dict, str(job_dir), job_id)

        # Normalize result (ensure lists and absolute paths)
        def _abs_list(lst):
            out = []
            for p in lst or []:
                if not isinstance(p, str):
                    continue
                # if path is relative, make it relative to job_dir
                pp = Path(p)
                if not pp.is_absolute():
                    pp = (job_dir / p).resolve()
                out.append(str(pp))
            return out

        norm_result: Dict[str, Any] = {}
        if isinstance(result, dict):
            norm_result.update(result)
            for key in ("clips", "thumbnails", "srts", "stabilized"):
                if key in norm_result:
                    norm_result[key] = _abs_list(norm_result.get(key))
        JOBS[job_id]["status"] = "finished"
        JOBS[job_id]["result"] = norm_result
        finish_ts = datetime.utcnow().isoformat() + "Z"
        _append_job_log(job_id, f"[{finish_ts}] FINISH result_keys={list(norm_result.keys())}")
        logger.info("Job %s: finished, result keys=%s", job_id, list(norm_result.keys()))
    except Exception as exc:
        tb = traceback.format_exc()
        _append_job_log(job_id, f"[{datetime.utcnow().isoformat()}Z] UNEXPECTED EXCEPTION: {exc}")
        _append_job_log(job_id, tb)
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = {"message": str(exc), "traceback": tb}
        logger.exception("Job %s: unexpected exception", job_id)

@app.post("/process")
async def process(recipe: Recipe, background_tasks: BackgroundTasks, request: Request):
    """
    Accept a recipe (JSON body) and create a job directory. If the recipe src is a local file that exists,
    create a per-job subfolder inside that source's parent directory and run l2s_core there so it behaves like the GUI
    while remaining safe for concurrent jobs.
    """
    job_id_local = str(uuid.uuid4())
    client_host = request.client.host if request.client else "unknown"
    # convert pydantic model to plain dict while preserving extra fields
    recipe_dict = json.loads(recipe.json()) if isinstance(recipe, Recipe) else recipe  # keeps existing behavior

    # Normalize file:// -> local paths if present in top-level src
    raw_src = recipe_dict.get("src")
    norm_src = _normalize_file_uri_to_path(raw_src)
    if norm_src is not None:
        recipe_dict["src"] = norm_src

    # Determine job_dir:
    # Always create a per-job subfolder. If src is a local file path that exists, place the subfolder inside the source's parent directory.
    job_dir_path = JOB_BASE_DIR / job_id_local
    try:
        src_path = str(recipe_dict.get("src")) if recipe_dict.get("src") is not None else None
        if src_path and isinstance(src_path, str):
            # expand user and make absolute
            sp = os.path.abspath(os.path.expanduser(src_path))
            if os.path.isfile(sp):
                # Create a subfolder named by job_id inside the source parent folder so l2s_core runs where the GUI ran
                parent = Path(sp).parent
                job_dir_path = parent / job_id_local
                job_dir_path.mkdir(parents=True, exist_ok=True)
                _append_job_log(job_id_local, f"[{datetime.utcnow().isoformat()}Z] Using source parent and creating job subfolder: {job_dir_path}")
            else:
                # src not a local existing file: create job dir under jobs/
                job_dir_path = JOB_BASE_DIR / job_id_local
                job_dir_path.mkdir(parents=True, exist_ok=True)
                _append_job_log(job_id_local, f"[{datetime.utcnow().isoformat()}Z] Source not local or doesn't exist; using job dir: {job_dir_path}")
        else:
            job_dir_path = JOB_BASE_DIR / job_id_local
            job_dir_path.mkdir(parents=True, exist_ok=True)
            _append_job_log(job_id_local, f"[{datetime.utcnow().isoformat()}Z] No src provided; using job dir: {job_dir_path}")
    except Exception as e:
        # fallback to default jobs/<job_id>
        job_dir_path = JOB_BASE_DIR / job_id_local
        job_dir_path.mkdir(parents=True, exist_ok=True)
        _append_job_log(job_id_local, f"[{datetime.utcnow().isoformat()}Z] Failed to inspect src path, using default job_dir: {e}")

    # write recipe file into job_dir_path as recipe.json (adapter/process_recipe expects recipe.json)
    recipe_path = Path(job_dir_path) / "recipe.json"
    try:
        with recipe_path.open("w", encoding="utf-8") as f:
            json.dump(recipe_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _append_job_log(job_id_local, f"[{datetime.utcnow().isoformat()}Z] Failed to write recipe.json into job_dir {job_dir_path}: {e}")
        # still record job info and schedule; adapter will fail and log the error.

    JOBS[job_id_local] = {
        "status": "accepted",
        "src": recipe_dict.get("src"),
        "job_dir": str(job_dir_path),
        "recipe_path": str(recipe_path),
        "result": {}
    }
    _append_job_log(job_id_local, f"[{datetime.utcnow().isoformat()}Z] SCHEDULED by {client_host} src={recipe_dict.get('src')} job_dir={job_dir_path} recipe_path={recipe_path}")
    logger.info("Received /process request from %s, created job %s, job_dir=%s", client_host, job_id_local, job_dir_path)
    # schedule background processing
    background_tasks.add_task(_process_job, job_id_local, job_dir_path)
    return {"status": "accepted", "job_id": job_id_local}

@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job

@app.get("/jobs/{job_id}/log")
async def get_job_log(job_id: str):
    p = JOB_RUN_DIR / f"{job_id}.log"
    if not p.exists():
        raise HTTPException(status_code=404, detail="job log not found")
    try:
        text = p.read_text(encoding="utf-8")
        return PlainTextResponse(content=text, status_code=200)
    except Exception:
        raise HTTPException(status_code=500, detail="failed to read job log")

@app.get("/jobs/{job_id}/artifacts")
async def get_job_artifacts(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(content=job.get("result", {}))

@app.get("/jobs/{job_id}/download")
async def download_job_file(job_id: str, path: Optional[str] = Query(None, description="Relative or absolute path to artifact")):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    result = job.get("result") or {}
    # If user provided path param, serve that file (resolve relative to job_dir)
    if path:
        p = Path(path)
        if not p.is_absolute():
            job_dir = Path(job.get("job_dir", "."))
            p = (job_dir / path).resolve()
    else:
        # default: try to serve first clip or first thumbnail
        clips = result.get("clips") or []
        thumbs = result.get("thumbnails") or result.get("thumbnails", []) or []
        candidate = None
        if isinstance(clips, list) and clips:
            candidate = clips[0]
        elif isinstance(thumbs, list) and thumbs:
            candidate = thumbs[0]
        else:
            candidate = None
        if not candidate:
            raise HTTPException(status_code=404, detail="no downloadable result for this job")
        p = Path(candidate)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"file not found: {p}")
    return FileResponse(path=str(p), media_type="application/octet-stream", filename=p.name)

@app.get("/")
async def root():
    return {"status": "ok", "jobs_count": len(JOBS)}