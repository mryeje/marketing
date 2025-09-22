from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from pathlib import Path
import os

router = APIRouter()

# Configuration via environment variables (fallbacks)
CLIPS_DIR = Path(os.getenv("CLIPS_DIR", r"C:\Users\mryej\AppData\Local\Temp")).resolve()
CLIP_TOKEN = os.getenv("CLIP_TOKEN", "")  # leave empty to disable token auth

class ClipEntry(BaseModel):
    filename: str
    url: str
    size_bytes: int

@router.get("/clips/list")
def list_clips(request: Request):
    """
    Return a JSON array of clips (filename, public URL, size).
    The URLs point to the /clips/download/{filename} endpoint and are built
    from request.base_url so they work through ngrok.
    """
    if not CLIPS_DIR.exists():
        raise HTTPException(status_code=500, detail=f"Clips directory does not exist: {CLIPS_DIR}")
    entries = []
    base = str(request.base_url).rstrip("/")  # e.g. https://abcd.ngrok.io
    for p in sorted(CLIPS_DIR.glob("*.mp4")):
        filename = p.name
        download_url = f"{base}/clips/download/{filename}"
        if CLIP_TOKEN:
            download_url = f"{download_url}?token={CLIP_TOKEN}"
        entries.append(ClipEntry(filename=filename, url=download_url, size_bytes=p.stat().st_size).dict())
    return JSONResponse({"clips": entries, "clips_dir": str(CLIPS_DIR)})

@router.get("/clips/download/{filename}")
def download_clip(filename: str, token: str = ""):
    """
    Secure download endpoint. If CLIP_TOKEN is set, token must match.
    Prevents path traversal and streams file as video/mp4.
    """
    if CLIP_TOKEN:
        if not token or token != CLIP_TOKEN:
            raise HTTPException(status_code=401, detail="Missing or invalid token")

    safe_path = (CLIPS_DIR / Path(filename).name).resolve()
    # ensure the resolved path is inside CLIPS_DIR
    if not str(safe_path).startswith(str(CLIPS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(safe_path), filename=safe_path.name, media_type="video/mp4")