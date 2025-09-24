#!/usr/bin/env python3
"""
plugin_proxy.py - Minimal ChatGPT plugin proxy that orchestrates a two-pass recipe run.

Behavior:
- Serves /.well-known/ai-plugin.json and /openapi.yaml (reads files in same dir).
- Exposes POST /submit_two_pass which accepts {"recipe": {...}, "two_pass": true}
- Validates Authorization: Bearer <PLUGIN_SECRET>
- For two_pass:
    1) POST {"recipe": ..., "phase":"overlay"} to PROCESS_URL and wait
    2) If overlay succeeded (HTTP 200), POST {"recipe": ..., "phase":"burn"} to PROCESS_URL and wait
- Returns combined JSON with the two responses.

Environment:
- PROCESS_URL (default http://localhost:8000/process) - where your server /process lives
- PLUGIN_SECRET (default "change-me-secret") - shared bearer token set in plugin config in ChatGPT
- HOST (default 0.0.0.0), PORT (default 3333)

Run:
  pip install fastapi uvicorn requests
  PLUGIN_SECRET="your-secret" PROCESS_URL="http://localhost:8000/process" uvicorn plugin_proxy:app --host 0.0.0.0 --port 3333
"""
from fastapi import FastAPI, Request, HTTPException, Header, Response
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional
import os
import json
import requests
import pathlib
import logging

app = FastAPI(title="L2S Submit Two-Pass Plugin Proxy")

# Config via env
PROCESS_URL = os.environ.get("PROCESS_URL", "http://localhost:8000/process")
PLUGIN_SECRET = os.environ.get("PLUGIN_SECRET", "change-me-secret")
STATIC_DIR = pathlib.Path(__file__).parent.resolve()
OPENAPI_PATH = STATIC_DIR / "openapi.yaml"
MANIFEST_PATH = STATIC_DIR / "ai-plugin.json"

# logger
logger = logging.getLogger("plugin_proxy")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

class SubmitTwoPassRequest(BaseModel):
    recipe: Dict[str, Any]
    two_pass: Optional[bool] = True
    wait_timeout_seconds: Optional[int] = 900  # per-phase timeout when proxy calls PROCESS_URL

def _require_bearer(authorization: Optional[str]) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    auth = authorization.strip()
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization must be Bearer token")
    token = auth.split(" ", 1)[1].strip()
    if token != PLUGIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid bearer token")

def _post_process(payload: Dict[str, Any], timeout: int = 900) -> Dict[str, Any]:
    """
    POST payload to PROCESS_URL and return simple dict with status_code and parsed body/text.
    """
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(PROCESS_URL, json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as ex:
        logger.exception("POST to PROCESS_URL failed")
        return {"status_code": 502, "error": str(ex), "body": None}
    body = None
    ct = resp.headers.get("content-type", "") or ""
    try:
        if "application/json" in ct.lower():
            body = resp.json()
        else:
            # try parse JSON as fallback
            try:
                body = resp.json()
            except Exception:
                body = resp.text
    except Exception:
        body = resp.text
    return {"status_code": resp.status_code, "body": body, "headers": dict(resp.headers)}

@app.get("/.well-known/ai-plugin.json", response_class=JSONResponse)
async def serve_manifest():
    if MANIFEST_PATH.exists():
        return JSONResponse(content=json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    return JSONResponse(content={
        "error": "ai-plugin.json not found on server"
    }, status_code=500)

@app.get("/openapi.yaml")
async def serve_openapi():
    if OPENAPI_PATH.exists():
        return FileResponse(str(OPENAPI_PATH), media_type="text/yaml")
    return PlainTextResponse("openapi.yaml not found", status_code=500)

@app.post("/submit_two_pass")
async def submit_two_pass(req: SubmitTwoPassRequest, authorization: Optional[str] = Header(None)):
    """
    Orchestrate two-pass processing.
    Expects Authorization: Bearer <PLUGIN_SECRET>.
    """
    _require_bearer(authorization)

    recipe = req.recipe
    two_pass = bool(req.two_pass)
    timeout = int(req.wait_timeout_seconds or 900)

    logger.info("Received submit_two_pass request (two_pass=%s) for recipe (clips=%d)", two_pass, len(recipe.get("clips", []) if isinstance(recipe, dict) else []))

    results = {"overlay": None, "burn": None, "errors": []}

    # Phase 1: overlay-only
    if two_pass:
        payload_overlay = {"recipe": recipe, "phase": "overlay"}
        logger.info("Posting overlay phase to PROCESS_URL=%s", PROCESS_URL)
        r1 = _post_process(payload_overlay, timeout=timeout)
        results["overlay"] = r1
        if r1.get("status_code", 500) != 200:
            results["errors"].append({"phase": "overlay", "reason": "overlay failed", "response": r1})
            logger.warning("Overlay phase failed (status %s). Not proceeding to burn.", r1.get("status_code"))
            return JSONResponse({"status": "overlay_failed", "results": results}, status_code=502)

    # Phase 2: burn subtitles - run regardless for two_pass==True only if overlay succeeded
    payload_burn = {"recipe": recipe, "phase": "burn"}
    logger.info("Posting burn phase to PROCESS_URL=%s", PROCESS_URL)
    r2 = _post_process(payload_burn, timeout=timeout)
    results["burn"] = r2
    if r2.get("status_code", 500) != 200:
        results["errors"].append({"phase": "burn", "reason": "burn failed", "response": r2})
        logger.warning("Burn phase failed (status %s).", r2.get("status_code"))
        return JSONResponse({"status": "burn_failed", "results": results}, status_code=502)

    logger.info("Two-pass processing completed successfully.")
    return JSONResponse({"status": "ok", "results": results})