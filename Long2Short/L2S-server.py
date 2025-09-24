# FastAPI wrapper exposing /process with tolerant input and robust import behavior.
# This patched version:
#  - fixes logging middleware so reading the body for logs doesn't break validation
#  - accepts either {"recipe": {...}} or the bare recipe with top-level "src"
#  - normalizes common typos (thumbnail_stragety -> thumbnail_strategy)
#  - converts local Windows paths to file:// URIs for Pydantic HttpUrl compatibility
#  - normalizes file:// back to local paths for processing
#  - tries an explicit import of l2s_core from the server directory and prints import errors
from fastapi import FastAPI, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ProxyHeadersMiddleware may not exist in older starlette versions; import conditionally
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
    _HAS_PROXY_HEADERS = True
except Exception:
    ProxyHeadersMiddleware = None
    _HAS_PROXY_HEADERS = False
    print("[WARN] starlette.middleware.proxy_headers.ProxyHeadersMiddleware not available; continuing without it. To enable, run: pip install --upgrade 'starlette'")

import uvicorn
import traceback
import importlib
import sys
import os
import inspect
import json
import tempfile
import urllib.parse
import pathlib
import re



from typing import Any
from models import ProcessRequest, ProcessResponse, ProcessOutput

# starlette Request class for replaying body
from starlette.requests import Request as StarletteRequest  # type: ignore

# Try to import the normalizer; if not present, continue but log.
try:
    from recipe_normalizer import normalize_recipe
    _HAS_NORMALIZER = True
    print("[INFO] recipe_normalizer imported")
except Exception as e:
    normalize_recipe = None
    _HAS_NORMALIZER = False
    print("[WARN] recipe_normalizer not available; proceeding without normalization. Error:", e)

app = FastAPI(title="Local L2S Processor (FastAPI wrapper - patched)")
from plugin_router import router as plugin_router
app.include_router(plugin_router)

# Respect ngrok / proxy X-Forwarded-* headers when available
if _HAS_PROXY_HEADERS:
    app.add_middleware(ProxyHeadersMiddleware)

# Allow simple cross-origin/preflight requests (use restrictive origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Simple middleware to log incoming requests (headers + body first N bytes)
# IMPORTANT: read the body for logging but re-create a request that replays the same body
# to downstream handlers. Otherwise FastAPI's request parsing/validation will see an empty body
# and return 422.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    print(f"[INCOMING] {client} {request.method} {request.url.path}")
    try:
        headers = dict(request.headers)
        # print only a subset to reduce noise
        print("[HEADERS]", {k: headers.get(k) for k in ("user-agent", "content-type", "content-length", "x-forwarded-for")})
    except Exception:
        pass

    # read the body (may be large) but keep a copy and re-inject it for downstream handlers
    body_bytes = b""
    try:
        body_bytes = await request.body()
        # print only first 2000 bytes to avoid log flooding
        body_preview = body_bytes[:2000].decode(errors="replace")
        print("[BODY]", body_preview)
    except Exception as e:
        print("[WARN] could not read request body for logging:", e)

    # Recreate an ASGI receive that will replay the body to downstream consumers.
    async def receive() -> dict:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    # Create a new Request instance that uses our receive replay function
    new_request = StarletteRequest(request.scope, receive)

    # Call the next handler with the new request that contains the same body
    response = await call_next(new_request)
    return response

# Simple health and informational endpoints
@app.get("/health")
async def health():
    return {"status": "ok", "message": "server running"}

@app.get("/")
async def root():
    return {"status": "ok", "openapi": "/openapi.json", "note": "POST /process to run processing"}

# Return a short helpful 200 on GET to /process so external probes don't see 405
@app.get("/process")
async def process_get():
    return {
        "status": "ok",
        "message": "This endpoint accepts POST with JSON body. See /openapi.json for schema."
    }

# Accept OPTIONS for preflight checks
@app.options("/process")
async def process_options():
    return {"allow": ["POST", "OPTIONS", "GET"]}

# Debug endpoint: echo headers, raw body and JSON parse result for diagnostics.
@app.post("/debug-echo")
async def debug_echo(request: Request):
    headers = dict(request.headers)
    raw = await request.body()
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = "<could not decode>"
    parsed = None
    parse_err = None
    try:
        parsed = json.loads(text) if text else None
    except Exception as e:
        parse_err = str(e)
    print("[DEBUG-ECHO] headers:", {k: headers.get(k) for k in ("user-agent", "content-type", "x-forwarded-for")})
    print("[DEBUG-ECHO] raw-preview:", (text[:2000] + ("..." if len(text) > 2000 else "")))
    if parse_err:
        print("[DEBUG-ECHO] parse-error:", parse_err)
    return JSONResponse({"headers": headers, "raw": text, "json": parsed, "parse_error": parse_err})

# TRY_IMPORT: try to find your existing processing function in likely modules.
process_func = None
_try_modules = [
    ("l2s_core", "process_recipe"),
    ("l2s_core", "process"),
    ("l2s", "process_recipe"),
    ("l2s", "process"),
    ("pipeline", "process_recipe"),
    ("L2S", "process_recipe"),
]

for mod_name, func_name in _try_modules:
    try:
        mod = __import__(mod_name, fromlist=[func_name])
        func = getattr(mod, func_name, None)
        if callable(func):
            process_func = func
            print(f"[INFO] Using processing function {mod_name}.{func_name}")
            break
    except Exception:
        # ignore import errors; continue trying
        pass

# If previous attempts didn't find a pipeline, try an explicit import from the server directory and print any import-time errors.
if process_func is None:
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        m = importlib.import_module("l2s_core")
        if hasattr(m, "process_recipe") and callable(m.process_recipe):
            process_func = m.process_recipe
            print("[INFO] Explicitly using l2s_core.process_recipe")
        elif hasattr(m, "process") and callable(m.process):
            process_func = m.process
            print("[INFO] Explicitly using l2s_core.process")
        else:
            print("[DEBUG] l2s_core imported but no callable process_recipe/process found")
    except Exception:
        print("[DEBUG] explicit import of l2s_core failed; pipeline will stay stubbed. Exception:")
        traceback.print_exc()

# If no function found, define a stub that mimics prior behavior.
def run_pipeline_stub(recipe: dict, skip_overlays: bool, use_cache: bool, debug: bool) -> dict:
    temp = os.environ.get("TEMP") or "/tmp"
    clip_path = os.path.join(temp, "c1_test.mp4")
    thumb_path = os.path.join(temp, "c1_test_thumb.jpg")
    return {
        "clips": [clip_path],
        "thumbnails": [thumb_path],
        "srts": [],
        "stabilized": [clip_path],
        "overlay_queue": None,
    }

def normalize_recipe_src(recipe: dict) -> None:
    """
    Recursively strip whitespace from all strings in the recipe dict in-place,
    and convert file:// URIs to local filesystem paths (Windows and POSIX).
    Safe no-op if recipe is missing or not a dict.
    """
    if not recipe or not isinstance(recipe, dict):
        return

    def strip_strings(obj):
        if isinstance(obj, str):
            return obj.strip()
        if isinstance(obj, list):
            return [strip_strings(i) for i in obj]
        if isinstance(obj, dict):
            return {k: strip_strings(v) for k, v in obj.items()}
        return obj

    try:
        cleaned = strip_strings(recipe)
        recipe.clear()
        recipe.update(cleaned)
    except Exception as e:
        print("[WARN] normalize_recipe_src: failed to strip strings:", e)
        return

    src = recipe.get("src")
    if isinstance(src, str) and src.startswith("file://"):
        path = urllib.parse.unquote(src[len("file://"):])
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        recipe["src"] = path
        print(f"[INFO] Normalized file URI to path: {src} -> {path}")

def try_call_processing(func, recipe: dict, req_dict: dict, skip_overlays: bool, use_cache: bool, debug: bool):
    """
    Try a series of sensible call signatures for the discovered processing function,
    including the common (recipe_path, args) signature. Returns the result dict.
    """
    errors = []
    try:
        sig = inspect.signature(func)
        param_names = [p.name for p in sig.parameters.values()]
    except Exception:
        sig = None
        param_names = []

    # If function looks like it expects a recipe file path + args, handle that first.
    if len(param_names) == 2:
        name0 = param_names[0].lower()
        name1 = param_names[1].lower()
        if ("path" in name0 or "recipe" in name0) and ("arg" in name1):
            print(f"[DEBUG] Detected signature ({param_names}), attempting recipe_path + args call")
            try:
                tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
                safe_recipe = jsonable_encoder(recipe)
                json.dump(safe_recipe, tmpf, ensure_ascii=False, indent=2)
                tmpf.flush()
                tmpf.close()
                tmp_path = tmpf.name
                args_val = req_dict.get("args", req_dict)
                result = func(tmp_path, args_val)
                print(f"[DEBUG] Called {func.__name__}({tmp_path}, args) successfully")
                return result
            finally:
                try:
                    if 'tmp_path' in locals() and os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

    # Fall back to a set of candidate call patterns
    call_patterns = []
    call_patterns.append(("kwargs_recipe", lambda: func(recipe=recipe, skip_overlays=skip_overlays, use_cache=use_cache, debug=debug)))
    call_patterns.append(("kwargs_req_dict", lambda: func(req_dict)))
    call_patterns.append(("single_recipe_arg", lambda: func(recipe)))
    call_patterns.append(("single_req_dict_arg", lambda: func(req_dict)))
    call_patterns.append(("positional_all", lambda: func(recipe, skip_overlays, use_cache, debug)))
    call_patterns.append(("positional_recipe_only", lambda: func(recipe,)))
    call_patterns.append(("unpack_req_kwargs", lambda: func(**req_dict)))
    call_patterns.append(("no_args", lambda: func()))

    last_exc = None
    for name, attempt in call_patterns:
        try:
            print(f"[DEBUG] Trying call pattern: {name}")
            result = attempt()
            print(f"[DEBUG] Call pattern {name} succeeded")
            return result
        except TypeError as te:
            errors.append((name, "TypeError", str(te)))
            last_exc = te
            print(f"[DEBUG] Call pattern {name} TypeError: {te}")
            continue
        except Exception as e:
            errors.append((name, e.__class__.__name__, str(e)))
            last_exc = e
            print(f"[DEBUG] Call pattern {name} raised {e.__class__.__name__}: {e}")
            continue

    msgs = ["All call attempts failed for processing function. Attempts:"]
    for attempt_name, exc_type, exc_msg in errors:
        msgs.append(f"- {attempt_name}: {exc_type}: {exc_msg}")
    raise RuntimeError("\n".join(msgs))

@app.post("/process", response_model=ProcessResponse)
async def process(request: Request):
    try:
        # Read raw JSON from client
        body = await request.json()

        # Accept either {"recipe": {...}} or a bare recipe object with top-level "src"
        if isinstance(body, dict) and "recipe" in body:
            wrapped = body
        elif isinstance(body, dict) and "src" in body:
            wrapped = {"recipe": body}
        else:
            wrapped = body

        # QUICK FIX: normalize common misspellings / legacy keys before validation
        if isinstance(wrapped, dict) and isinstance(wrapped.get("recipe"), dict):
            r = wrapped["recipe"]
            # common misspelling reported: thumbnail_stragety -> thumbnail_strategy
            if "thumbnail_stragety" in r and "thumbnail_strategy" not in r:
                r["thumbnail_strategy"] = r.pop("thumbnail_stragety")
            # Log unexpected keys to help debugging
            known_keys = {
                "src","style_profile","generate_thumbnails","add_text_overlay","multi_platform",
                "platforms","overlay_text_template","thumbnail_strategy","thumbnail_filename_template",
                "caption_style","highlight_style","clips","thumbnail_time","thumbnail_filename"
            }
            extra_keys = [k for k in r.keys() if k not in known_keys]
            if extra_keys:
                print(f"[DEBUG] recipe contains unexpected keys (will be ignored or may be normalized): {extra_keys}")

        # Normalize recipe.src to a file:// URI if it's a local path without a scheme.
        try:
            if isinstance(wrapped, dict) and isinstance(wrapped.get("recipe"), dict):
                src_val = wrapped["recipe"].get("src")
                if isinstance(src_val, str) and src_val.strip():
                    # If there's no scheme like "http://" or "file://", convert local path to file://
                    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", src_val):
                        abs_path = os.path.abspath(src_val)
                        try:
                            file_uri = pathlib.Path(abs_path).as_uri()  # e.g. file:///C:/...
                        except Exception:
                            p = abs_path.replace("\\", "/")
                            if os.name == "nt" and not p.startswith("/"):
                                p = "/" + p
                            file_uri = "file://" + urllib.parse.quote(p)
                        wrapped["recipe"]["src"] = file_uri
        except Exception as ex:
            print("[WARN] src normalization failed:", ex)

        # Insert / replace the SERVER-SIDE NORMALIZATION block with this debug-enhanced variant.
# Place this where the prior "SERVER-SIDE NORMALIZATION: run recipe_normalizer" logic lives.

# SERVER-SIDE NORMALIZATION + DEBUG DUMP: run recipe_normalizer (if available) before validation
        if _HAS_NORMALIZER:
            try:
                wrapped = normalize_recipe(wrapped)
                print("[INFO] Recipe normalized by recipe_normalizer")
                # Debug dump: write normalized payload to a temp file for inspection by user
                try:
                    norm_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".normalized.json", delete=False, encoding="utf-8")
                    json.dump(wrapped, norm_tmp, ensure_ascii=False, indent=2)
                    norm_tmp.flush()
                    norm_tmp_path = norm_tmp.name
                    norm_tmp.close()
                    print(f"[DEBUG] Wrote normalized recipe to: {norm_tmp_path}")
                    # Log clip summary (count + ids + first clip preview)
                    try:
                        recipe_obj = wrapped.get("recipe", wrapped) if isinstance(wrapped, dict) else wrapped
                        clips = recipe_obj.get("clips", []) if isinstance(recipe_obj, dict) else []
                        print(f"[DEBUG] Normalized recipe clips count: {len(clips)}")
                        if isinstance(clips, list) and clips:
                            ids = [c.get("id", f"<no-id-{i}>") for i, c in enumerate(clips, start=1)]
                            print(f"[DEBUG] Normalized recipe clip ids: {ids}")
                            # print a trimmed preview of the first clip
                            import copy
                            first_clip = copy.deepcopy(clips[0])
                            # redact large fields if any
                            print("[DEBUG] First clip preview:", json.dumps(first_clip, ensure_ascii=False, indent=2)[:2000])
                    except Exception as e:
                        print("[WARN] Unable to extract clip summary from normalized recipe:", e)
                except Exception as e:
                    print("[WARN] Could not write normalized recipe to temp file:", e)
            except Exception as ex:
                print("[ERROR] recipe_normalizer failed:", ex)
                traceback.print_exc()
                # Return a clear 400 so clients see the normalization error
                raise HTTPException(status_code=400, detail={"status": "error", "message": "recipe normalization failed", "detail": str(ex)})
        else:
            print("[WARN] recipe_normalizer not present; skipping normalization. Recommend adding recipe_normalizer.py to server directory.")

        # Validate using the existing Pydantic model
        try:
            req = ProcessRequest.parse_obj(wrapped)
        except Exception as ex:
            # Re-raise with logging so client gets clear error details
            print("[ERROR] Validation failed for incoming request:", ex)
            raise

        # Support Pydantic v2 and v1 accessors
        req_dict = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        recipe = req_dict.get("recipe")

        # Convert file:// URIs back to local paths for downstream processing
        try:
            normalize_recipe_src(recipe)
        except Exception as e:
            print("[WARN] normalize_recipe_src failed:", e)
        skip_overlays = req_dict.get("skip_overlays", False)
        use_cache = req_dict.get("use_cache", True)
        debug = req_dict.get("debug", False)

        if process_func:
            try:
                result = try_call_processing(process_func, recipe, req_dict, skip_overlays, use_cache, debug)
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail={"status": "error", "message": str(e)})
        else:
            print("[WARN] No pipeline import found; using stubbed response")
            result = run_pipeline_stub(recipe, skip_overlays, use_cache, debug)

        output = {
            "clips": result.get("clips", []),
            "thumbnails": result.get("thumbnails", []),
            "srts": result.get("srts", []),
            "stabilized": result.get("stabilized", []),
            "overlay_queue": result.get("overlay_queue"),
        }
        resp = ProcessResponse(status="ok", message="processed", output=output)
        return resp
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail={"status": "error", "message": str(e)})

if __name__ == "__main__":
    uvicorn.run("L2S-server:app", host="0.0.0.0", port=8000, reload=True)