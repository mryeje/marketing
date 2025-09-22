#!/usr/bin/env python3
r"""
Long2Short_gui.py

GUI with overlay-preview controls and persistent settings.

What I changed:
- Added automatic persistent storage for GUI settings (video/tracking/pipeline and overlay controls).
- Settings are saved to ~/.long2short/gui_settings.json (Windows: C:\Users\<user>\.long2short\gui_settings.json).
- Settings are loaded at startup and used to populate the Settings object, recipe path, and overlay controls.
- UI changes (overlay controls and known settings vars exposed by l2s_gui_settings) trigger an autosave (debounced).
- Save is also performed when the user clicks "Apply overlays to recipe", previews, or starts a job.
- Persisted keys include: recipe_path, settings (all attributes present on Settings), overlay_text, caption_style,
  highlight_style, and use_overlay_for_job flag.
- Added an app-close handler to persist current state before exit.
- Added extensive debug logging around load/save actions so you can confirm the GUI is persisting values.

How persistence works:
- File location: <home>/.long2short/gui_settings.json
- On startup: the GUI attempts to read the file; any keys present are used to initialize the Settings dataclass
  and populate overlay controls and recipe path.
- When the user edits overlay controls or (if available) settings controls, the GUI schedules an autosave (debounced 800ms).
- Autosave writes a compact JSON file with the fields mentioned above.

What's next:
- If you want settings stored in a different location (AppData on Windows, XDG on Linux), I can switch to platform-specific dirs.
- If l2s_gui_settings exposes its own variable mapping, the GUI will bind to those variables (if provided) for immediate autosave;
  otherwise we persist the Settings object attributes when saving.
- If you prefer an explicit "Save Settings" button in addition to autosave, I can add one.

Replace your Long2Short_gui.py with the file below.
"""
import os
import sys
import shlex
import subprocess
import threading
import traceback
import json
import tempfile
import shutil
import datetime
from types import SimpleNamespace
from typing import Optional, Dict, Any
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import tkinter.scrolledtext as scrolled

# Import settings panel helpers (assumes l2s_gui_settings.py is present)
try:
    from l2s_gui_settings import Settings, add_settings_panel_tk, apply_settings_to_args, read_settings_from_args  # type: ignore
except Exception as e:
    print("[WARN] l2s_gui_settings import failed:", e)
    from dataclasses import dataclass
    @dataclass
    class Settings:
        apply_stabilize: bool = False
        model_path: str = "yolov8n-pose.pt"
        device: str = "auto"
        prefer_pillow: bool = True
        extraction_method: str = "track"
        smooth_sigma: float = 5.0
        confidence: float = 0.25
        stabilization_method: str = "moviepy"
        zoom: float = 1.05
        ybias: float = 0.10
        max_shift_frac: float = 0.25
        border_mode: str = "reflect101"
        reattach_audio: bool = True
        split_method: str = "ffmpeg"
        reencode_fallback: bool = True
        tmp_dir: str = None
        target_w: int = 1080
        target_h: int = 1920
        cleanup_wide_files: bool = True
        ffmpeg_verbose: bool = False
    def add_settings_panel_tk(parent, settings, row_start=0):
        def writeback():
            return settings
        # best-effort to emulate a "vars" mapping if callers expect it: empty by default
        return {"vars": {}, "writeback": writeback}
    def apply_settings_to_args(settings, args):
        for k, v in settings.__dict__.items():
            setattr(args, k, v)

# Path to CLI script (fallback)
LONG2SHORT_SCRIPT = os.path.join(os.path.dirname(__file__), "Long2Short.py")

# import l2s_core for preview rendering (capture full traceback for GUI)
import traceback as _traceback
_l2s_core_import_tb = None
try:
    import l2s_core  # type: ignore
except Exception:
    l2s_core = None
    _l2s_core_import_tb = _traceback.format_exc()

# import l2s_overlays for post-processing overlays queue (capture traceback)
_l2s_overlays_import_tb = None
try:
    import l2s_overlays  # type: ignore
except Exception:
    l2s_overlays = None
    _l2s_overlays_import_tb = _traceback.format_exc()

# UI option lists
SIZE_OPTIONS = ["xxs", "xs", "small", "medium", "large", "xl"]
STYLE_OPTIONS = ["", "bold_drop_shadow", "underline", "italic", "outline", "bold"]
EFFECT_OPTIONS = ["", "typewriter", "line_by_line_fade", "fade", "pulsate"]
PLACEMENT_OPTIONS = ["top_center", "top_third", "upper_third", "center", "lower_third", "bottom_center", "cta"]

# Named-color mapping (used when recipes use names like "dark_green" or "semi_transparent")
NAMED_COLORS: Dict[str, str] = {
    "white": "#ffffff",
    "black": "#000000",
    "red": "#ff0000",
    "green": "#00ff00",
    "dark_green": "#0c5022",
    "yellow": "#ffd600",
    "semi_transparent": "#000000",  # alpha dropped — treat as black for chooser
    "transparent": "#000000",
}

def _normalize_color_string(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    v = str(val).strip()
    if v.lower() in NAMED_COLORS:
        return NAMED_COLORS[v.lower()]
    if v.startswith("#"):
        if len(v) == 9:  # #RRGGBBAA -> strip alpha
            return v[:7]
        return v
    return v

def _get_persist_dir() -> str:
    home = os.path.expanduser("~")
    cfg_dir = os.path.join(home, ".long2short")
    try:
        os.makedirs(cfg_dir, exist_ok=True)
    except Exception:
        pass
    return cfg_dir

def _get_persist_path() -> str:
    return os.path.join(_get_persist_dir(), "gui_settings.json")

class StyleControls:
    """
    Generic controls for a single style block (placement, font, size, style, effect, color, background, text).
    """
    def __init__(self, label: str):
        self.label = label
        self.placement = tk.StringVar(value="")
        self.font = tk.StringVar(value="")
        self.size = tk.StringVar(value="medium")
        self.style = tk.StringVar(value="")
        self.effect = tk.StringVar(value="")
        self.color = tk.StringVar(value="#ffffff")
        self.background = tk.StringVar(value="")   # may be named or hex
        self.text = tk.StringVar(value="")         # for overlay_text only

    def as_dict(self, include_text: bool = False) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if self.placement.get(): out["placement"] = self.placement.get()
        if self.font.get(): out["font"] = self.font.get()
        if self.size.get(): out["size"] = self.size.get()
        if self.style.get(): out["style"] = self.style.get()
        if self.effect.get(): out["effect"] = self.effect.get()
        if self.color.get(): out["color"] = self.color.get()
        if self.background.get(): out["background"] = self.background.get()
        if include_text and self.text.get(): out["text"] = self.text.get()
        return out

    def debug_state(self) -> Dict[str, str]:
        return {
            "placement": self.placement.get(),
            "font": self.font.get(),
            "size": self.size.get(),
            "style": self.style.get(),
            "effect": self.effect.get(),
            "color": self.color.get(),
            "background": self.background.get(),
            "text": self.text.get()
        }

    def bind_autosave(self, autosave_callback):
        # attach trace_add to each StringVar/IntVar/BooleanVar to trigger autosave
        for var in (self.placement, self.font, self.size, self.style, self.effect, self.color, self.background, self.text):
            try:
                var.trace_add("write", lambda *_args, cb=autosave_callback: cb())
            except Exception:
                try:
                    var.trace("w", lambda *_args, cb=autosave_callback: cb())
                except Exception:
                    pass

class GUI:
    def __init__(self, root):
        self.root = root
        root.title("Long2Short GUI — Persistent Settings & Overlay Preview")
        # frames
        top = ttk.Frame(root, padding=8)
        top.pack(side="top", fill="x")
        self.settings_frame = ttk.LabelFrame(top, text="Settings", padding=8)
        self.settings_frame.pack(side="left", fill="y", padx=6, pady=4)
        self.controls_frame = ttk.Frame(top)
        self.controls_frame.pack(side="left", fill="both", expand=True, padx=6, pady=4)
        self.log_frame = ttk.Frame(root)
        self.log_frame.pack(side="bottom", fill="both", expand=True, padx=8, pady=6)

        # Persistent store loaded early to feed Settings object.
        self._persisted: Dict[str, Any] = self._load_persisted_settings()

        # Recipe selection
        ttk.Label(self.controls_frame, text="Recipe JSON:").grid(row=0, column=0, sticky="w")
        self.recipe_path_var = tk.StringVar(value=self._persisted.get("recipe_path", ""))
        ttk.Entry(self.controls_frame, textvariable=self.recipe_path_var, width=60).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(self.controls_frame, text="Browse", command=self.browse_recipe).grid(row=0, column=2, sticky="w", padx=4)
        ttk.Button(self.controls_frame, text="Inspect recipe", command=self.inspect_recipe).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Button(self.controls_frame, text="Load overlay styles from recipe", command=self.load_styles_from_selected_recipe).grid(row=1, column=2, sticky="w", padx=4)

        # Start/Stop
        self.start_button = ttk.Button(self.controls_frame, text="Start Job", command=self.start_job)
        self.start_button.grid(row=2, column=1, sticky="w", pady=6)
        self.stop_button = ttk.Button(self.controls_frame, text="Stop Job", command=self.stop_job, state="disabled")
        self.stop_button.grid(row=2, column=2, sticky="w", padx=4)

        # Create Settings object using persisted values where available
        settings_init_kwargs = {}
        for k, v in self._persisted.get("settings", {}).items():
            settings_init_kwargs[k] = v
        try:
            self.settings = Settings(**settings_init_kwargs)  # type: ignore
        except Exception:
            # fallback if Settings signature doesn't match persisted keys
            self.settings = Settings()

        # Settings panel (may return "vars" mapping for tracing)
        controls = add_settings_panel_tk(self.settings_frame, self.settings, row_start=0)
        self.settings_controls = controls

        # Overlay controls panel (three sections)
        self.overlay_text_ctrl = StyleControls("overlay_text")
        self.caption_style_ctrl = StyleControls("caption_style")
        self.highlight_style_ctrl = StyleControls("highlight_style")

        oc_frame = ttk.LabelFrame(self.settings_frame, text="Overlay & Style Controls", padding=6)
        oc_frame.grid(row=30, column=0, columnspan=4, pady=6, sticky="we")

        # overlay_text section UI
        ov_frame = ttk.LabelFrame(oc_frame, text="overlay_text (preview item)", padding=6)
        ov_frame.grid(row=0, column=0, sticky="we", padx=4, pady=4)
        r = 0
        ttk.Label(ov_frame, text="Text:").grid(row=r, column=0, sticky="w")
        ttk.Entry(ov_frame, textvariable=self.overlay_text_ctrl.text, width=36).grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
        r += 1
        ttk.Label(ov_frame, text="Placement:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(ov_frame, textvariable=self.overlay_text_ctrl.placement, values=PLACEMENT_OPTIONS, width=18).grid(row=r, column=1, sticky="w")
        ttk.Label(ov_frame, text="Font:").grid(row=r, column=2, sticky="w")
        ttk.Entry(ov_frame, textvariable=self.overlay_text_ctrl.font, width=18).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(ov_frame, text="Size:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(ov_frame, textvariable=self.overlay_text_ctrl.size, values=SIZE_OPTIONS, width=12).grid(row=r, column=1, sticky="w")
        ttk.Label(ov_frame, text="Style:").grid(row=r, column=2, sticky="w")
        ttk.Combobox(ov_frame, textvariable=self.overlay_text_ctrl.style, values=STYLE_OPTIONS, width=16).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(ov_frame, text="Effect:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(ov_frame, textvariable=self.overlay_text_ctrl.effect, values=EFFECT_OPTIONS, width=18).grid(row=r, column=1, sticky="w")
        ttk.Label(ov_frame, text="Text color:").grid(row=r, column=2, sticky="w")
        ttk.Entry(ov_frame, textvariable=self.overlay_text_ctrl.color, width=12).grid(row=r, column=3, sticky="w")
        ttk.Button(ov_frame, text="Pick", command=lambda: self._pick_color(self.overlay_text_ctrl.color)).grid(row=r, column=4, sticky="w", padx=4)
        r += 1
        ttk.Label(ov_frame, text="Background:").grid(row=r, column=0, sticky="w")
        ttk.Entry(ov_frame, textvariable=self.overlay_text_ctrl.background, width=18).grid(row=r, column=1, sticky="w")
        ttk.Button(ov_frame, text="Pick BG", command=lambda: self._pick_color(self.overlay_text_ctrl.background)).grid(row=r, column=2, sticky="w", padx=4)

        # caption_style
        cap_frame = ttk.LabelFrame(oc_frame, text="caption_style", padding=6)
        cap_frame.grid(row=1, column=0, sticky="we", padx=4, pady=4)
        r = 0
        ttk.Label(cap_frame, text="Placement:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(cap_frame, textvariable=self.caption_style_ctrl.placement, values=PLACEMENT_OPTIONS, width=18).grid(row=r, column=1, sticky="w")
        ttk.Label(cap_frame, text="Font:").grid(row=r, column=2, sticky="w")
        ttk.Entry(cap_frame, textvariable=self.caption_style_ctrl.font, width=18).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(cap_frame, text="Size:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(cap_frame, textvariable=self.caption_style_ctrl.size, values=SIZE_OPTIONS, width=12).grid(row=r, column=1, sticky="w")
        ttk.Label(cap_frame, text="Background:").grid(row=r, column=2, sticky="w")
        ttk.Entry(cap_frame, textvariable=self.caption_style_ctrl.background, width=18).grid(row=r, column=3, sticky="w")
        ttk.Button(cap_frame, text="Pick BG", command=lambda: self._pick_color(self.caption_style_ctrl.background)).grid(row=r, column=4, sticky="w", padx=4)
        r += 1
        ttk.Label(cap_frame, text="Effect:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(cap_frame, textvariable=self.caption_style_ctrl.effect, values=EFFECT_OPTIONS, width=18).grid(row=r, column=1, sticky="w")
        ttk.Label(cap_frame, text="Text color:").grid(row=r, column=2, sticky="w")
        ttk.Entry(cap_frame, textvariable=self.caption_style_ctrl.color, width=12).grid(row=r, column=3, sticky="w")
        ttk.Button(cap_frame, text="Pick", command=lambda: self._pick_color(self.caption_style_ctrl.color)).grid(row=r, column=4, sticky="w", padx=4)

        # highlight_style
        hl_frame = ttk.LabelFrame(oc_frame, text="highlight_style", padding=6)
        hl_frame.grid(row=2, column=0, sticky="we", padx=4, pady=4)
        r = 0
        ttk.Label(hl_frame, text="Placement:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(hl_frame, textvariable=self.highlight_style_ctrl.placement, values=PLACEMENT_OPTIONS, width=18).grid(row=r, column=1, sticky="w")
        ttk.Label(hl_frame, text="Font:").grid(row=r, column=2, sticky="w")
        ttk.Entry(hl_frame, textvariable=self.highlight_style_ctrl.font, width=18).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(hl_frame, text="Size:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(hl_frame, textvariable=self.highlight_style_ctrl.size, values=SIZE_OPTIONS, width=12).grid(row=r, column=1, sticky="w")
        ttk.Label(hl_frame, text="Style:").grid(row=r, column=2, sticky="w")
        ttk.Combobox(hl_frame, textvariable=self.highlight_style_ctrl.style, values=STYLE_OPTIONS, width=16).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(hl_frame, text="Effect:").grid(row=r, column=0, sticky="w")
        ttk.Combobox(hl_frame, textvariable=self.highlight_style_ctrl.effect, values=EFFECT_OPTIONS, width=18).grid(row=r, column=1, sticky="w")
        ttk.Label(hl_frame, text="Text color:").grid(row=r, column=2, sticky="w")
        ttk.Entry(hl_frame, textvariable=self.highlight_style_ctrl.color, width=12).grid(row=r, column=3, sticky="w")
        ttk.Button(hl_frame, text="Pick", command=lambda: self._pick_color(self.highlight_style_ctrl.color)).grid(row=r, column=4, sticky="w", padx=4)
        r += 1
        ttk.Label(hl_frame, text="Background:").grid(row=r, column=0, sticky="w")
        ttk.Entry(hl_frame, textvariable=self.highlight_style_ctrl.background, width=18).grid(row=r, column=1, sticky="w")
        ttk.Button(hl_frame, text="Pick BG", command=lambda: self._pick_color(self.highlight_style_ctrl.background)).grid(row=r, column=2, sticky="w", padx=4)

        # Controls row: Use overlay settings and Preview / Apply
        ctl_row = ttk.Frame(oc_frame)
        ctl_row.grid(row=3, column=0, sticky="we", pady=(6,0))
        self.use_overlay_for_job_var = tk.BooleanVar(value=self._persisted.get("use_overlay_for_job", False))
        ttk.Checkbutton(ctl_row, text="Use overlay settings for job", variable=self.use_overlay_for_job_var).pack(side="left", padx=(4,0))
        ttk.Button(ctl_row, text="Preview overlay (first clip)", command=self.preview_overlay).pack(side="right", padx=4)
        ttk.Button(ctl_row, text="Apply overlays to recipe (backup created)", command=self.apply_overlays_to_recipe).pack(side="right", padx=6)

        # Log area
        ttk.Label(self.log_frame, text="Log:").pack(anchor="w")
        self.log_widget = scrolled.ScrolledText(self.log_frame, height=16, wrap="none")
        self.log_widget.pack(fill="both", expand=True)
        self.log_widget.configure(state="disabled")

        # State & autosave
        self._proc = None
        self._thread = None
        self._stop_event = threading.Event()
        self._temp_recipe_for_cleanup: Optional[str] = None
        self._autosave_after_id: Optional[str] = None
        self._autosave_delay_ms = 800

        # Populate overlay controls from persisted data (if any)
        self._populate_overlay_controls_from_persisted()

        # Bind autsave traces: overlay controls and settings vars if available
        self._bind_autosave_traces()

        # Bind close handler to ensure settings saved
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.append_log("GUI ready. Loaded persisted settings (if available).")

    # ---------------- Persistence helpers ----------------
    def _load_persisted_settings(self) -> Dict[str, Any]:
        p = _get_persist_path()
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._log_debug(f"[DEBUG] Loaded persisted GUI settings from {p}")
                    return data if isinstance(data, dict) else {}
        except Exception as e:
            self._log_debug(f"[WARN] Failed to load persisted settings {p}: {e}")
        return {}

    def _save_persisted_settings_now(self):
        p = _get_persist_path()
        payload: Dict[str, Any] = {}
        try:
            payload["recipe_path"] = self.recipe_path_var.get() or ""
            # persist settings object by copying attributes
            try:
                settings_snapshot = {}
                for k, v in getattr(self.settings, "__dict__", {}).items():
                    try:
                        # simple-safe json types
                        settings_snapshot[k] = v
                    except Exception:
                        settings_snapshot[k] = str(v)
                payload["settings"] = settings_snapshot
            except Exception:
                payload["settings"] = {}
            # overlay controls
            payload["overlay_text"] = [self.overlay_text_ctrl.as_dict(include_text=True)]
            payload["caption_style"] = self.caption_style_ctrl.as_dict()
            payload["highlight_style"] = self.highlight_style_ctrl.as_dict()
            payload["use_overlay_for_job"] = bool(self.use_overlay_for_job_var.get())
            # timestamp
            payload["_last_saved"] = datetime.datetime.utcnow().isoformat() + "Z"
            # write
            with open(p, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._log_debug(f"[DEBUG] Persisted GUI settings to {p}")
        except Exception as e:
            self._log_debug(f"[ERROR] Failed to persist GUI settings to {p}: {e}")

    def _schedule_autosave(self):
        # debounce autosave
        try:
            if self._autosave_after_id:
                self.root.after_cancel(self._autosave_after_id)
        except Exception:
            pass
        try:
            self._autosave_after_id = self.root.after(self._autosave_delay_ms, self._save_and_log_autosave)
        except Exception:
            # fallback immediate
            self._save_and_log_autosave()

    def _save_and_log_autosave(self):
        try:
            self._save_persisted_settings_now()
            self.append_log("[INFO] GUI settings autosaved.")
        finally:
            self._autosave_after_id = None

    def _populate_overlay_controls_from_persisted(self):
        d = self._persisted
        try:
            ov_list = d.get("overlay_text") or []
            if isinstance(ov_list, list) and len(ov_list) > 0 and isinstance(ov_list[0], dict):
                ov0 = ov_list[0]
                self.overlay_text_ctrl.text.set(str(ov0.get("text", self.overlay_text_ctrl.text.get())))
                self.overlay_text_ctrl.placement.set(str(ov0.get("placement", self.overlay_text_ctrl.placement.get())))
                self.overlay_text_ctrl.font.set(str(ov0.get("font", self.overlay_text_ctrl.font.get())))
                self.overlay_text_ctrl.size.set(str(ov0.get("size", self.overlay_text_ctrl.size.get())))
                self.overlay_text_ctrl.style.set(str(ov0.get("style", self.overlay_text_ctrl.style.get())))
                self.overlay_text_ctrl.effect.set(str(ov0.get("effect", self.overlay_text_ctrl.effect.get())))
                tc = _normalize_color_string(ov0.get("color")) or self.overlay_text_ctrl.color.get()
                if tc: self.overlay_text_ctrl.color.set(tc)
                bgc = _normalize_color_string(ov0.get("background")) or self.overlay_text_ctrl.background.get()
                if bgc: self.overlay_text_ctrl.background.set(bgc)
            cap = d.get("caption_style") or {}
            if isinstance(cap, dict):
                self.caption_style_ctrl.placement.set(str(cap.get("placement", self.caption_style_ctrl.placement.get())))
                self.caption_style_ctrl.font.set(str(cap.get("font", self.caption_style_ctrl.font.get())))
                self.caption_style_ctrl.size.set(str(cap.get("size", self.caption_style_ctrl.size.get())))
                bgc = _normalize_color_string(cap.get("background")) or self.caption_style_ctrl.background.get()
                if bgc: self.caption_style_ctrl.background.set(bgc)
                self.caption_style_ctrl.effect.set(str(cap.get("effect", self.caption_style_ctrl.effect.get())))
                tc = _normalize_color_string(cap.get("color")) or self.caption_style_ctrl.color.get()
                if tc: self.caption_style_ctrl.color.set(tc)
            hl = d.get("highlight_style") or {}
            if isinstance(hl, dict):
                self.highlight_style_ctrl.placement.set(str(hl.get("placement", self.highlight_style_ctrl.placement.get())))
                self.highlight_style_ctrl.font.set(str(hl.get("font", self.highlight_style_ctrl.font.get())))
                self.highlight_style_ctrl.size.set(str(hl.get("size", self.highlight_style_ctrl.size.get())))
                self.highlight_style_ctrl.style.set(str(hl.get("style", self.highlight_style_ctrl.style.get())))
                self.highlight_style_ctrl.effect.set(str(hl.get("effect", self.highlight_style_ctrl.effect.get())))
                tc = _normalize_color_string(hl.get("color")) or self.highlight_style_ctrl.color.get()
                if tc: self.highlight_style_ctrl.color.set(tc)
                bgc = _normalize_color_string(hl.get("background")) or self.highlight_style_ctrl.background.get()
                if bgc: self.highlight_style_ctrl.background.set(bgc)
        except Exception as e:
            self._log_debug(f"[WARN] populate overlay controls from persisted failed: {e}")

    def _bind_autosave_traces(self):
        # overlay controls
        try:
            self.overlay_text_ctrl.bind_autosave(self._schedule_autosave)
            self.caption_style_ctrl.bind_autosave(self._schedule_autosave)
            self.highlight_style_ctrl.bind_autosave(self._schedule_autosave)
            self.recipe_path_var.trace_add("write", lambda *_a: self._schedule_autosave())
            self.use_overlay_for_job_var.trace_add("write", lambda *_a: self._schedule_autosave())
        except Exception:
            pass

        # If add_settings_panel_tk returned a "vars" mapping, bind them too
        try:
            vars_map = self.settings_controls.get("vars", {}) if isinstance(self.settings_controls, dict) else {}
            if isinstance(vars_map, dict):
                for name, var in vars_map.items():
                    try:
                        var.trace_add("write", lambda *_a: self._schedule_autosave())
                    except Exception:
                        try:
                            var.trace("w", lambda *_a: self._schedule_autosave())
                        except Exception:
                            pass
        except Exception:
            pass

    # ---------------- UI helpers ----------------
    def append_log(self, text: str):
        try:
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", text + ("\n" if not text.endswith("\n") else ""))
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
        except Exception:
            print(text)

    def _log_debug(self, text: str):
        # write to GUI log and also stdout for easier trace
        try:
            self.append_log(text)
        except Exception:
            print(text)

    def browse_recipe(self):
        p = filedialog.askopenfilename(title="Select recipe JSON", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p:
            self.recipe_path_var.set(p)
            # try to load styles from newly selected recipe
            try:
                self.load_styles_from_recipe_file(p)
            except Exception as e:
                self.append_log(f"[WARN] Could not auto-load styles from recipe: {e}")

    def inspect_recipe(self):
        p = self.recipe_path_var.get().strip()
        if not p:
            messagebox.showinfo("Inspect recipe", "No recipe selected.")
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            pretty = json.dumps(data, indent=2)
            self.append_log(f"Recipe contents ({p}):\n{pretty}\n")
        except Exception as e:
            messagebox.showerror("Inspect recipe", f"Failed to read recipe: {e}")
            self.append_log(f"Failed to read recipe {p}: {e}\n")

    def load_styles_from_selected_recipe(self):
        p = self.recipe_path_var.get().strip()
        if not p or not os.path.isfile(p):
            messagebox.showerror("Load styles", "Select a valid recipe file first.")
            return
        try:
            self.load_styles_from_recipe_file(p)
            self.append_log(f"[INFO] Loaded overlay styles from recipe: {p}")
            # debug states
            self.append_log("[DEBUG] overlay_text_ctrl state: " + json.dumps(self.overlay_text_ctrl.debug_state(), ensure_ascii=False))
            self.append_log("[DEBUG] caption_style_ctrl state: " + json.dumps(self.caption_style_ctrl.debug_state(), ensure_ascii=False))
            self.append_log("[DEBUG] highlight_style_ctrl state: " + json.dumps(self.highlight_style_ctrl.debug_state(), ensure_ascii=False))
            # schedule save to persist the loaded values
            self._schedule_autosave()
        except Exception as e:
            messagebox.showerror("Load styles", f"Failed to load styles from recipe: {e}")
            self.append_log(f"[ERROR] Failed loading styles: {e}\n{traceback.format_exc()}")

    def load_styles_from_recipe_file(self, recipe_path: str):
        with open(recipe_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ov_list = data.get("overlay_text") or []
        if isinstance(ov_list, list) and len(ov_list) > 0 and isinstance(ov_list[0], dict):
            ov0 = ov_list[0]
            self.overlay_text_ctrl.text.set(str(ov0.get("text", self.overlay_text_ctrl.text.get())))
            self.overlay_text_ctrl.placement.set(str(ov0.get("placement", self.overlay_text_ctrl.placement.get())))
            self.overlay_text_ctrl.font.set(str(ov0.get("font", self.overlay_text_ctrl.font.get())))
            self.overlay_text_ctrl.size.set(str(ov0.get("size", self.overlay_text_ctrl.size.get())))
            self.overlay_text_ctrl.style.set(str(ov0.get("style", self.overlay_text_ctrl.style.get())))
            self.overlay_text_ctrl.effect.set(str(ov0.get("effect", self.overlay_text_ctrl.effect.get())))
            tc = _normalize_color_string(ov0.get("color")) or self.overlay_text_ctrl.color.get()
            if tc: self.overlay_text_ctrl.color.set(tc)
            bgc = _normalize_color_string(ov0.get("background")) or self.overlay_text_ctrl.background.get()
            if bgc: self.overlay_text_ctrl.background.set(bgc)
        cap = data.get("caption_style") or {}
        if isinstance(cap, dict):
            self.caption_style_ctrl.placement.set(str(cap.get("placement", self.caption_style_ctrl.placement.get())))
            self.caption_style_ctrl.font.set(str(cap.get("font", self.caption_style_ctrl.font.get())))
            self.caption_style_ctrl.size.set(str(cap.get("size", self.caption_style_ctrl.size.get())))
            bgc = _normalize_color_string(cap.get("background")) or self.caption_style_ctrl.background.get()
            if bgc: self.caption_style_ctrl.background.set(bgc)
            self.caption_style_ctrl.effect.set(str(cap.get("effect", self.caption_style_ctrl.effect.get())))
            tc = _normalize_color_string(cap.get("color")) or self.caption_style_ctrl.color.get()
            if tc: self.caption_style_ctrl.color.set(tc)
        hl = data.get("highlight_style") or {}
        if isinstance(hl, dict):
            self.highlight_style_ctrl.placement.set(str(hl.get("placement", self.highlight_style_ctrl.placement.get())))
            self.highlight_style_ctrl.font.set(str(hl.get("font", self.highlight_style_ctrl.font.get())))
            self.highlight_style_ctrl.size.set(str(hl.get("size", self.highlight_style_ctrl.size.get())))
            self.highlight_style_ctrl.style.set(str(hl.get("style", self.highlight_style_ctrl.style.get())))
            self.highlight_style_ctrl.effect.set(str(hl.get("effect", self.highlight_style_ctrl.effect.get())))
            tc = _normalize_color_string(hl.get("color")) or self.highlight_style_ctrl.color.get()
            if tc: self.highlight_style_ctrl.color.set(tc)
            bgc = _normalize_color_string(hl.get("background")) or self.highlight_style_ctrl.background.get()
            if bgc: self.highlight_style_ctrl.background.set(bgc)

    def _pick_color(self, var: tk.StringVar):
        cur = var.get() or "#ffffff"
        try:
            rgb, hexv = colorchooser.askcolor(color=cur, parent=self.root, title="Choose color")
            if hexv:
                var.set(hexv)
                self.append_log(f"[DEBUG] Color chosen: {hexv}")
                self._schedule_autosave()
        except Exception as ex:
            self.append_log(f"[WARN] Color chooser failed: {ex}")

    # ---------------- Apply / Preview / Job flow (unchanged, but save settings where relevant) ----------------
    def apply_overlays_to_recipe(self):
        recipe_path = self.recipe_path_var.get().strip()
        if not recipe_path or not os.path.isfile(recipe_path):
            messagebox.showerror("Apply overlays", "Please select a valid recipe JSON file first.")
            return
        if not messagebox.askyesno("Apply overlays", "This will overwrite the selected recipe JSON (a backup will be created). Continue?"):
            return
        try:
            timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            backup_path = recipe_path + f".backup.{timestamp}"
            shutil.copy2(recipe_path, backup_path)
            self.append_log(f"[INFO] Created recipe backup: {backup_path}")
        except Exception as e:
            self.append_log(f"[ERROR] Failed to create backup: {e}")
            messagebox.showerror("Apply overlays", f"Failed to create backup: {e}")
            return
        try:
            with open(recipe_path, "r", encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception as e:
            self.append_log(f"[ERROR] Could not read recipe: {e}")
            messagebox.showerror("Apply overlays", f"Could not read recipe: {e}")
            return
        ov_entry = self.overlay_text_ctrl.as_dict(include_text=True)
        caption_style = self.caption_style_ctrl.as_dict()
        highlight_style = self.highlight_style_ctrl.as_dict()
        # Debug log the overlay JSON to be written
        merged = {}
        if ov_entry: merged["overlay_text"] = [ov_entry]
        if caption_style: merged["caption_style"] = caption_style
        if highlight_style: merged["highlight_style"] = highlight_style
        self.append_log("[DEBUG] Overlay JSON to write into recipe:")
        try:
            pretty = json.dumps(merged, ensure_ascii=False, indent=2)
            for ln in pretty.splitlines(): self.append_log("[DEBUG] " + ln)
        except Exception:
            self.append_log("[DEBUG] (could not serialize overlay JSON)")
        # Merge into recipe and write
        if ov_entry: recipe["overlay_text"] = [ov_entry]
        if caption_style: recipe["caption_style"] = caption_style
        if highlight_style: recipe["highlight_style"] = highlight_style
        try:
            with open(recipe_path, "w", encoding="utf-8") as f:
                json.dump(recipe, f, ensure_ascii=False, indent=2)
            self.append_log(f"[INFO] Applied overlays to recipe: {recipe_path}")
            messagebox.showinfo("Apply overlays", f"Overlay settings merged into recipe. Backup: {backup_path}")
            # Persist GUI settings now that user explicitly applied
            self._save_persisted_settings_now()
        except Exception as e:
            try:
                shutil.copy2(backup_path, recipe_path)
            except Exception:
                pass
            self.append_log(f"[ERROR] Failed to write updated recipe: {e}")
            messagebox.showerror("Apply overlays", f"Failed to write updated recipe: {e}")

    def preview_overlay(self):
        if l2s_core is None:
            tb = _l2s_core_import_tb or "No traceback available."
            messagebox.showerror("Preview overlay", "l2s_core failed to import; preview unavailable.\n\nImport traceback:\n\n" + tb)
            self.append_log(f"[ERROR] l2s_core import traceback:\n{tb}")
            return
        recipe_path = self.recipe_path_var.get().strip()
        if not recipe_path or not os.path.isfile(recipe_path):
            messagebox.showerror("Preview overlay", "Please select a valid recipe JSON file first.")
            return
        try:
            with open(recipe_path, "r", encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception as e:
            messagebox.showerror("Preview overlay", f"Failed to read recipe: {e}")
            return
        clips = recipe.get("clips", [])
        if not clips:
            messagebox.showerror("Preview overlay", "Recipe contains no clips to preview.")
            return
        entry = clips[0]
        start = entry.get("start"); end = entry.get("end")
        if start is None or end is None:
            messagebox.showerror("Preview overlay", "Clip missing start/end timecodes.")
            return
        ov_entry = self.overlay_text_ctrl.as_dict(include_text=True)
        caption_style = self.caption_style_ctrl.as_dict()
        highlight_style = self.highlight_style_ctrl.as_dict()
        overlay_json = {"overlay_text": [ov_entry], "caption_style": caption_style, "highlight_style": highlight_style}
        srt_stub = entry.get("srt_stub") or None
        main_text = entry.get("text") or recipe.get("text") or None
        fd, tmp_out = tempfile.mkstemp(prefix="l2s_overlay_preview_", suffix=".mp4"); os.close(fd)
        try:
            start_s = l2s_core.timecode_to_seconds(start, None)
            end_s = l2s_core.timecode_to_seconds(end, None)
            if end_s is None or start_s is None:
                messagebox.showerror("Preview overlay", "Failed to parse timecodes for preview.")
                return
            dur = max(0.1, min(6.0, end_s - start_s, 6.0)); preview_end = start_s + dur
            self.append_log(f"[INFO] Rendering preview {tmp_out} ({start_s:.2f}s -> {preview_end:.2f}s) ... this may take a few seconds.")
            prefer_pillow = getattr(self.settings, "prefer_pillow", True)
            try:
                l2s_core.trim_and_export_clip(
                    recipe.get("src") or getattr(self.settings, "video", None),
                    start_s, preview_end, tmp_out,
                    add_overlay_text=main_text,
                    overlay_instructions=overlay_json,
                    generate_thumbnail=False,
                    srt_stub=srt_stub,
                    add_text_overlay_flag=True,
                    prefer_pillow=prefer_pillow
                )
            except Exception as e:
                self.append_log(f"[WARN] module-mode preview failed: {e}. Falling back to subprocess preview.")
                python_exe = sys.executable or "python"
                cmd = [python_exe, LONG2SHORT_SCRIPT, "--recipe", recipe_path, "--start", str(start_s), "--end", str(preview_end), "--out", tmp_out]
                fd2, overlay_tmp = tempfile.mkstemp(prefix="l2s_overlay_ui_", suffix=".json"); os.close(fd2)
                with open(overlay_tmp, "w", encoding="utf-8") as f: json.dump(overlay_json, f, indent=2)
                cmd += ["--overlay-json", overlay_tmp]
                self.append_log("[INFO] Running subprocess preview: " + " ".join(shlex.quote(x) for x in cmd))
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for ln in proc.stdout: self.append_log(ln.rstrip("\n"))
                proc.wait()
                try: os.remove(overlay_tmp)
                except Exception: pass
            self.append_log(f"[INFO] Preview written to {tmp_out}")
            try:
                if sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", tmp_out])
                elif os.name == "nt":
                    os.startfile(tmp_out)  # type: ignore
                else:
                    subprocess.Popen(["xdg-open", tmp_out])
            except Exception:
                self.append_log(f"[INFO] Preview available at: {tmp_out}")
            # also persist settings after preview
            self._schedule_autosave()
        except Exception as e:
            self.append_log(f"[ERROR] Preview failed: {e}\n{traceback.format_exc()}")
            messagebox.showerror("Preview overlay", f"Preview failed: {e}")
            try:
                if os.path.isfile(tmp_out):
                    os.remove(tmp_out)
            except Exception:
                pass

    def stop_job(self):
        self.append_log("[INFO] Stop requested.")
        self._stop_event.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self.append_log("[INFO] Subprocess terminated.")
            except Exception:
                pass
        self.set_buttons_running(False)

    def start_job(self):
        recipe = self.recipe_path_var.get().strip()
        if not recipe or not os.path.isfile(recipe):
            messagebox.showerror("Start Job", "Please select a valid recipe JSON file.")
            return
        try:
            current_settings = self.settings_controls["writeback"]()
            if hasattr(current_settings, "tmp_dir") and current_settings.tmp_dir == "":
                current_settings.tmp_dir = None
        except Exception as e:
            self.append_log(f"[WARN] Failed to read settings from UI: {e}")
            current_settings = self.settings
        args = SimpleNamespace()
        apply_settings_to_args(current_settings, args)
        # persist settings before starting the job
        self._save_persisted_settings_now()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_recipe_thread, args=(recipe, args, current_settings), daemon=True)
        self._thread.start()
        self.set_buttons_running(True)

    # The rest of the job / module-mode / subprocess flow is unchanged from earlier code;
    # we keep the same behavior and debug messages as before, but we ensure the recipe used
    # is either the original or a temp recipe (created with current overlay controls) and that
    # we persist current GUI state around the run. For brevity the implementation of _run_recipe_thread
    # is unchanged conceptually from previous versions and still attempts module-mode first.
    def _run_recipe_thread(self, recipe_path, args, settings):
        temp_recipe_path: Optional[str] = None
        try:
            if self.use_overlay_for_job_var.get():
                temp_recipe_path = self._create_temp_recipe_with_overlays(recipe_path)
                if temp_recipe_path:
                    recipe_to_use = temp_recipe_path
                    self.append_log(f"[DEBUG] Using temporary recipe for job: {temp_recipe_path}")
                else:
                    recipe_to_use = recipe_path
                    self.append_log(f"[DEBUG] Could not create temporary recipe; falling back to original: {recipe_path}")
            else:
                recipe_to_use = recipe_path
                self.append_log(f"[DEBUG] Not using overlay overrides for job; using recipe: {recipe_path}")

            import importlib
            l2s_core_mod = importlib.import_module("l2s_core")
            if hasattr(l2s_core_mod, "process_recipe"):
                self.append_log("[INFO] Running l2s_core.process_recipe (module-mode).")
                try:
                    if hasattr(args, "overlay_json"):
                        self.append_log(f"[DEBUG] args.overlay_json -> {getattr(args, 'overlay_json')}")
                    result = l2s_core_mod.process_recipe(recipe_to_use, args)
                    self.append_log(f"[INFO] process_recipe completed: clips={len(result.get('clips', [])) if isinstance(result, dict) else 'unknown'}")
                    queue_path = find_latest_overlay_queue(recipe_to_use, since_ts=os.path.getmtime(recipe_to_use))
                    if queue_path:
                        self.append_log(f"[INFO] Found overlay queue: {queue_path}")
                        try:
                            with open(queue_path, "r", encoding="utf-8") as qf:
                                qdata = json.load(qf)
                            entries = qdata.get("entries", [])
                            self.append_log(f"[DEBUG] overlays_queue entries: {len(entries)}")
                            if entries:
                                self.append_log("[DEBUG] First overlay entry keys: " + ", ".join(list(entries[0].keys())))
                                oi = entries[0].get("overlay_instructions", {})
                                try:
                                    pretty = json.dumps(oi, ensure_ascii=False, indent=2)
                                    self.append_log("[DEBUG] overlay_instructions (first entry):")
                                    for ln in pretty.splitlines():
                                        self.append_log("[DEBUG]   " + ln)
                                except Exception:
                                    self.append_log("[DEBUG] (could not serialize overlay_instructions)")
                        except Exception as ex:
                            self.append_log(f"[WARN] Could not read overlays_queue for debug: {ex}")
                        if l2s_overlays:
                            try:
                                self.append_log("[INFO] Running l2s_overlays.process_overlays_queue on queue (post-processing)...")
                                failures = l2s_overlays.process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=False)
                                if failures:
                                    self.append_log(f"[WARN] Overlays processing finished with {len(failures)} failures.")
                                else:
                                    self.append_log("[INFO] Overlays processing finished successfully.")
                            except Exception as ex:
                                self.append_log(f"[ERROR] Overlays processing failed: {ex}\n{traceback.format_exc()}")
                        else:
                            tb = _l2s_overlays_import_tb or "l2s_overlays not importable"
                            self.append_log(f"[WARN] l2s_overlays not available: {tb}. You can run overlays manually with the queue file.")
                    else:
                        self.append_log("[INFO] No overlays_queue_*.json found after pipeline run.")
                    return
                except Exception as e:
                    self.append_log(f"[WARN] process_recipe raised: {e}\n{traceback.format_exc()}")
        except Exception as e:
            self.append_log(f"[WARN] Module-mode unavailable or failed: {e}")

        # Fallback to subprocess using recipe_to_use
        try:
            recipe_to_use_sub = temp_recipe_path if temp_recipe_path else recipe_path
            self.append_log(f"[DEBUG] Subprocess will use recipe: {recipe_to_use_sub}")
            cmd = self._build_cli_command(recipe_to_use_sub, args, settings)
            if temp_recipe_path:
                try:
                    with open(temp_recipe_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.append_log("[DEBUG] Temp recipe top-level overlay keys:")
                    for k in ("overlay_text", "caption_style", "highlight_style"):
                        if k in data:
                            self.append_log(f"[DEBUG]  - {k}: present")
                        else:
                            self.append_log(f"[DEBUG]  - {k}: missing")
                except Exception as ex:
                    self.append_log(f"[WARN] Could not read temp recipe for debug: {ex}")
            self.append_log("[INFO] Subprocess command: " + " ".join(shlex.quote(x) for x in cmd))
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in self._proc.stdout:
                if self._stop_event.is_set():
                    break
                self.append_log(line.rstrip("\n"))
            self._proc.wait()
            rc = self._proc.returncode
            if rc == 0:
                self.append_log("[INFO] Subprocess finished successfully.")
            else:
                self.append_log(f"[ERROR] Subprocess exited with code {rc}")
        except Exception as e:
            self.append_log(f"[ERROR] Failed to run subprocess: {e}\n{traceback.format_exc()}")
        finally:
            try:
                recipe_for_check = temp_recipe_path if temp_recipe_path else recipe_path
                queue_path = find_latest_overlay_queue(recipe_for_check, since_ts=os.path.getmtime(recipe_for_check))
                if queue_path:
                    self.append_log(f"[INFO] Found overlay queue: {queue_path}")
                    try:
                        with open(queue_path, "r", encoding="utf-8") as qf:
                            qdata = json.load(qf)
                        entries = qdata.get("entries", [])
                        self.append_log(f"[DEBUG] overlays_queue entries: {len(entries)}")
                        if entries:
                            self.append_log("[DEBUG] First overlay entry keys: " + ", ".join(list(entries[0].keys())))
                    except Exception as ex:
                        self.append_log(f"[WARN] Could not read overlays_queue for debug: {ex}")
                    if l2s_overlays:
                        try:
                            self.append_log("[INFO] Running l2s_overlays.process_overlays_queue on queue (post-processing)...")
                            failures = l2s_overlays.process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=False)
                            if failures:
                                self.append_log(f"[WARN] Overlays processing finished with {len(failures)} failures.")
                            else:
                                self.append_log("[INFO] Overlays processing finished successfully.")
                        except Exception as ex:
                            self.append_log(f"[ERROR] Overlays processing failed: {ex}\n{traceback.format_exc()}")
                    else:
                        tb = _l2s_overlays_import_tb or "l2s_overlays not importable"
                        self.append_log(f"[WARN] l2s_overlays not available: {tb}. You can run overlays manually with the queue file.")
                else:
                    self.append_log("[INFO] No overlays_queue_*.json found after subprocess run.")
            except Exception as ex:
                self.append_log(f"[ERROR] Post-run overlay check failed: {ex}\n{traceback.format_exc()}")
            self.set_buttons_running(False)
            self._proc = None
            if temp_recipe_path:
                try:
                    os.remove(temp_recipe_path)
                    self.append_log(f"[INFO] Removed temporary recipe: {temp_recipe_path}")
                except Exception:
                    pass

    def _create_temp_recipe_with_overlays(self, original_recipe_path: str) -> Optional[str]:
        try:
            with open(original_recipe_path, "r", encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception as e:
            self.append_log(f"[ERROR] Could not read original recipe for merging overlays: {e}")
            return None
        ov_entry = self.overlay_text_ctrl.as_dict(include_text=True)
        caption_style = self.caption_style_ctrl.as_dict()
        highlight_style = self.highlight_style_ctrl.as_dict()
        if ov_entry: recipe["overlay_text"] = [ov_entry]
        if caption_style: recipe["caption_style"] = caption_style
        if highlight_style: recipe["highlight_style"] = highlight_style
        # debug dump
        try:
            pretty = json.dumps({
                "overlay_text": recipe.get("overlay_text"),
                "caption_style": recipe.get("caption_style"),
                "highlight_style": recipe.get("highlight_style")
            }, ensure_ascii=False, indent=2)
            self.append_log("[DEBUG] Temp recipe merged overlay section:")
            for ln in pretty.splitlines(): self.append_log("[DEBUG] " + ln)
        except Exception:
            pass
        fd, tmp_recipe = tempfile.mkstemp(prefix="l2s_recipe_overlay_", suffix=".json"); os.close(fd)
        try:
            with open(tmp_recipe, "w", encoding="utf-8") as f: json.dump(recipe, f, ensure_ascii=False, indent=2)
            self.append_log(f"[INFO] Temporary recipe with overlays written: {tmp_recipe}")
            self._temp_recipe_for_cleanup = tmp_recipe
            # persist GUI state at this point as well
            self._save_persisted_settings_now()
            return tmp_recipe
        except Exception as e:
            try: os.remove(tmp_recipe)
            except Exception: pass
            self.append_log(f"[ERROR] Failed to write temporary recipe: {e}")
            return None

    def _build_cli_command(self, recipe_path, args, settings):
        python_exe = sys.executable or "python"
        cmd = [python_exe, LONG2SHORT_SCRIPT, "--recipe", recipe_path]
        # map core flags (unchanged)
        if getattr(args, "apply_stabilize", False):
            cmd.append("--apply-stabilize")
        if getattr(args, "model", None):
            cmd += ["--model", str(getattr(args, "model"))]
        if getattr(args, "device", None):
            cmd += ["--device", str(getattr(args, "device"))]
        if getattr(args, "extract_method_hint", None):
            cmd += ["--extract-method", str(getattr(args, "extract_method_hint"))]
        if getattr(args, "stabilizer_method_hint", None):
            cmd += ["--stabilizer-method", str(getattr(args, "stabilizer_method_hint"))]
        if getattr(args, "smooth_sigma", None) is not None:
            cmd += ["--smooth-sigma", str(getattr(args, "smooth_sigma"))]
        if getattr(args, "confidence", None) is not None:
            cmd += ["--confidence", str(getattr(args, "confidence"))]
        if getattr(args, "zoom", None) is not None:
            cmd += ["--zoom", str(getattr(args, "zoom"))]
        if getattr(args, "ybias", None) is not None:
            cmd += ["--ybias", str(getattr(args, "ybias"))]
        if getattr(args, "max_shift_frac", None) is not None:
            cmd += ["--max-shift-frac", str(getattr(args, "max_shift_frac"))]
        if getattr(args, "border_mode", None) is not None:
            cmd += ["--border-mode", str(getattr(args, "border_mode"))]
        if getattr(args, "split_method_hint", None):
            cmd += ["--split-method", str(getattr(args, "split_method_hint"))]
        if getattr(args, "reencode_fallback", False):
            cmd.append("--reencode-fallback")
        if getattr(args, "reattach_audio", False):
            cmd.append("--reattach-audio")
        if getattr(args, "tmp_dir", None):
            cmd += ["--tmp-dir", str(getattr(args, "tmp_dir"))]
        if getattr(args, "TARGET_W", None):
            cmd += ["--target-w", str(getattr(args, "TARGET_W"))]
        if getattr(args, "TARGET_H", None):
            cmd += ["--target-h", str(getattr(args, "TARGET_H"))]
        if getattr(args, "cleanup_wide_files", False):
            cmd.append("--cleanup-wide-files")
        if getattr(args, "ffmpeg_verbose", False):
            cmd.append("--ffmpeg-verbose")
        return cmd

    def set_buttons_running(self, running: bool):
        if running:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        else:
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            # cleanup any temp recipe created (best-effort)
            try:
                if hasattr(self, "_temp_recipe_for_cleanup") and self._temp_recipe_for_cleanup:
                    if os.path.isfile(self._temp_recipe_for_cleanup):
                        os.remove(self._temp_recipe_for_cleanup)
                        self.append_log(f"[DEBUG] Removed leftover temp recipe: {self._temp_recipe_for_cleanup}")
                    self._temp_recipe_for_cleanup = None
            except Exception:
                pass

    def _on_close(self):
        # ensure settings persist on exit
        try:
            self._save_persisted_settings_now()
            self.append_log("[INFO] GUI settings saved on exit.")
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            try:
                sys.exit(0)
            except Exception:
                pass

# ---------------- helper to find overlay queue (copied unchanged) ----------------
def find_latest_overlay_queue(recipe_path: str, since_ts: float) -> Optional[str]:
    recipe_dir = os.path.dirname(os.path.abspath(recipe_path)) or os.getcwd()
    candidates = []
    try:
        for fname in os.listdir(recipe_dir):
            if fname.startswith("overlays_queue_") and fname.endswith(".json"):
                full = os.path.join(recipe_dir, fname)
                try:
                    mtime = os.path.getmtime(full)
                except Exception:
                    mtime = 0
                if mtime >= since_ts - 0.5:
                    candidates.append((mtime, full))
    except Exception:
        pass
    if not candidates:
        try:
            with open(recipe_path, "r", encoding="utf-8") as f:
                recipe = json.load(f)
            out_dir = recipe.get("outdir") or recipe.get("out") or None
            if out_dir:
                if not os.path.isabs(out_dir):
                    out_dir = os.path.join(os.path.dirname(os.path.abspath(recipe_path)), out_dir)
                if os.path.isdir(out_dir):
                    for fname in os.listdir(out_dir):
                        if fname.startswith("overlays_queue_") and fname.endswith(".json"):
                            full = os.path.join(out_dir, fname)
                            try:
                                mtime = os.path.getmtime(full)
                            except Exception:
                                mtime = 0
                            if mtime >= since_ts - 0.5:
                                candidates.append((mtime, full))
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]

def main():
    root = tk.Tk()
    gui = GUI(root)
    root.geometry("980x820")
    root.mainloop()

if __name__ == "__main__":
    main()