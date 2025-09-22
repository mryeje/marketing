from __future__ import annotations
from typing import Any, List, Optional, Union, Dict
from pydantic import BaseModel, HttpUrl, Field

# Minimal, defensive models used by L2S-server.
# Adjusted for Pydantic v2: use Field(..., alias=...) instead of Config.fields,
# and use default_factory for list defaults.

class OverlayEntry(BaseModel):
    text: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None
    placement: Optional[str] = None
    font: Optional[str] = None
    size: Optional[Any] = None
    style: Optional[str] = None
    effect: Optional[str] = None
    color: Optional[str] = None
    background: Optional[str] = None

class SubtitleEntry(BaseModel):
    # Use Field alias so incoming JSON can use key "from"
    from_: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    text: Optional[str] = None

    # If you want to allow populating by attribute name as well as alias:
    model_config = {"populate_by_name": True}

class Clip(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    start: Optional[Union[str, float]] = None
    end: Optional[Union[str, float]] = None
    duration_sec: Optional[float] = None
    overlay_text: Optional[List[OverlayEntry]] = Field(default_factory=list)
    subtitles: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class Recipe(BaseModel):
    # Accept remote HTTP(S) URLs as HttpUrl, but also accept plain strings (local paths or file:// URIs).
    src: Union[HttpUrl, str]
    style_profile: Optional[str] = None
    generate_thumbnails: Optional[bool] = True
    add_text_overlay: Optional[bool] = True
    multi_platform: Optional[bool] = False
    platforms: Optional[List[str]] = Field(default_factory=list)
    overlay_text_template: Optional[str] = None
    thumbnail_strategy: Optional[str] = None
    thumbnail_filename_template: Optional[str] = None
    caption_style: Optional[Dict[str, Any]] = Field(default_factory=dict)
    highlight_style: Optional[Dict[str, Any]] = Field(default_factory=dict)
    clips: Optional[List[Clip]] = Field(default_factory=list)

class ProcessOutput(BaseModel):
    clips: List[str] = Field(default_factory=list)
    thumbnails: List[str] = Field(default_factory=list)
    srts: List[str] = Field(default_factory=list)
    stabilized: List[str] = Field(default_factory=list)
    overlay_queue: Optional[Any] = None

class ProcessResponse(BaseModel):
    status: str
    message: Optional[str] = None
    output: Optional[ProcessOutput] = None

class ProcessRequest(BaseModel):
    # The server expects a top-level "recipe" field. Keep that shape.
    recipe: Recipe
    skip_overlays: Optional[bool] = False
    use_cache: Optional[bool] = True
    debug: Optional[bool] = False