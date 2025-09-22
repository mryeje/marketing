"""
l2s_gui_settings.py

Helpers to expose new stabilization / extraction / splitting settings to a Tkinter-based GUI
and to map them into the command/args object consumed by Long2Short / l2s_core.process_recipe.

This variant includes:
- confidence slider (0.0 - 1.0) with live numeric readout
- cleanup_wide_files checkbox: remove intermediate wide/trimmed file after vertical stabilized file
- mapping of these new settings into args via apply_settings_to_args
"""
from dataclasses import dataclass
from typing import Optional
import os

# tkinter is only used for the helper that constructs a panel; GUI can ignore this file if not using tkinter
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    TK_AVAILABLE = True
except Exception:
    tk = None
    ttk = None
    messagebox = None
    filedialog = None
    TK_AVAILABLE = False

# Provide a lightweight Settings container that the GUI can bind to
@dataclass
class Settings:
    # Core
    apply_stabilize: bool = False
    model_path: str = "yolov8n-pose.pt"
    device: str = "auto"               # "auto"|"cpu"|"cuda"
    prefer_pillow: bool = True

    # Extraction / tracking
    extraction_method: str = "track"   # "track" | "framewise"
    smooth_sigma: float = 5.0
    confidence: float = 0.25           # detection confidence threshold (0.0 - 1.0)

    # Stabilization / crop
    stabilization_method: str = "moviepy"   # "moviepy" | "opencv"
    zoom: float = 1.05
    ybias: float = 0.10
    max_shift_frac: float = 0.25
    border_mode: str = "reflect101"         # reflect101, reflect, replicate, wrap, constant
    reattach_audio: bool = True             # used when stabilization_method == "opencv"

    # Splitting / trimming
    split_method: str = "ffmpeg"            # "ffmpeg" | "moviepy"
    reencode_fallback: bool = True

    # Output / temp
    tmp_dir: Optional[str] = None
    target_w: int = 1080
    target_h: int = 1920
    cleanup_wide_files: bool = True         # delete wide trimmed files after successful vertical stab

    # Verbose / debugging
    ffmpeg_verbose: bool = False

    def as_dict(self):
        return self.__dict__.copy()


def apply_settings_to_args(settings: Settings, args):
    """
    Map the Settings values onto an args-like object expected by Long2Short/l2s_core.
    This mutates args in-place.
    """
    # Core
    setattr(args, "apply_stabilize", bool(settings.apply_stabilize))
    setattr(args, "model", settings.model_path)
    setattr(args, "device", settings.device)
    setattr(args, "prefer_pillow", bool(settings.prefer_pillow))

    # Extraction
    setattr(args, "extract_method_hint", settings.extraction_method)
    setattr(args, "smooth_sigma", float(settings.smooth_sigma))
    setattr(args, "confidence", float(settings.confidence))

    # Stabilization
    setattr(args, "stabilizer_method_hint", settings.stabilization_method)
    setattr(args, "zoom", float(settings.zoom))
    setattr(args, "ybias", float(settings.ybias))
    setattr(args, "max_shift_frac", float(settings.max_shift_frac))
    setattr(args, "border_mode", settings.border_mode)
    # Only meaningful for opencv method
    setattr(args, "reattach_audio", bool(settings.reattach_audio))

    # Splitting/trimming
    setattr(args, "split_method_hint", settings.split_method)
    setattr(args, "reencode_fallback", bool(settings.reencode_fallback))

    # Misc
    setattr(args, "tmp_dir", settings.tmp_dir)
    setattr(args, "TARGET_W", int(settings.target_w))
    setattr(args, "TARGET_H", int(settings.target_h))
    setattr(args, "ffmpeg_verbose", bool(settings.ffmpeg_verbose))
    setattr(args, "cleanup_wide_files", bool(settings.cleanup_wide_files))


def read_settings_from_args(args) -> Settings:
    """
    Create a Settings instance populated from an args-like object (used to initialize GUI controls).
    Missing attributes fall back to defaults.
    """
    s = Settings()
    for k in s.__dict__.keys():
        try:
            if hasattr(args, k):
                setattr(s, k, getattr(args, k))
        except Exception:
            pass
    # special mappings / common alternate names
    if hasattr(args, "model"):
        s.model_path = getattr(args, "model")
    if hasattr(args, "device"):
        s.device = getattr(args, "device")
    if hasattr(args, "smooth_sigma"):
        s.smooth_sigma = getattr(args, "smooth_sigma")
    if hasattr(args, "confidence"):
        s.confidence = getattr(args, "confidence")
    if hasattr(args, "cleanup_wide_files"):
        s.cleanup_wide_files = getattr(args, "cleanup_wide_files")
    return s


# ----------------- Tkinter UI helpers -----------------
def add_settings_panel_tk(parent, settings: Settings, row_start: int = 0):
    """
    Add a compact settings panel into a Tk parent widget.
    Returns a dict of control variables (tk.Variable) keyed by setting name.

    Parent is expected to be a tk.Frame or similar. This function requires Tkinter to be available.
    """
    if not TK_AVAILABLE:
        raise RuntimeError("Tkinter not available in this Python environment")

    vars_map = {}

    def _make_label(text, r, c=0, sticky="w"):
        lbl = ttk.Label(parent, text=text)
        lbl.grid(row=r, column=c, sticky=sticky, padx=4, pady=2)
        return lbl

    def _attach_value_label(var, lbl, fmt="{:.2f}"):
        # update label when var changes
        def _upd(*_):
            try:
                v = var.get()
                lbl.config(text=fmt.format(v))
            except Exception:
                lbl.config(text=str(var.get()))
        # use trace_add where available
        try:
            var.trace_add("write", _upd)
        except Exception:
            try:
                var.trace("w", _upd)
            except Exception:
                pass
        _upd()

    r = row_start

    # Apply stabilize checkbox
    vars_map["apply_stabilize"] = tk.BooleanVar(value=settings.apply_stabilize)
    cb = ttk.Checkbutton(parent, text="Apply stabilization", variable=vars_map["apply_stabilize"])
    cb.grid(row=r, column=0, columnspan=4, sticky="w", padx=4, pady=2)
    r += 1

    # Model path + device
    _make_label("Model path:", r)
    vars_map["model_path"] = tk.StringVar(value=settings.model_path)
    e = ttk.Entry(parent, textvariable=vars_map["model_path"], width=36)
    e.grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    def _browse_model():
        p = filedialog.askopenfilename(title="Select YOLO model", filetypes=[("PyTorch", "*.pt *.pth"), ("All files", "*.*")])
        if p:
            vars_map["model_path"].set(p)
    ttk.Button(parent, text="Browse", command=_browse_model).grid(row=r, column=3, sticky="w", padx=4)
    r += 1

    _make_label("Device:", r)
    vars_map["device"] = tk.StringVar(value=settings.device)
    ttk.OptionMenu(parent, vars_map["device"], settings.device, "auto", "cpu", "cuda").grid(row=r, column=1, sticky="w", padx=4)
    r += 1

    # Extraction method + smooth sigma + confidence
    _make_label("Extraction method:", r)
    vars_map["extraction_method"] = tk.StringVar(value=settings.extraction_method)
    ttk.OptionMenu(parent, vars_map["extraction_method"], settings.extraction_method, "track", "framewise").grid(row=r, column=1, sticky="w", padx=4)
    r += 1

    _make_label("Smoothing sigma:", r)
    vars_map["smooth_sigma"] = tk.DoubleVar(value=settings.smooth_sigma)
    s_sigma = ttk.Scale(parent, from_=0.0, to=20.0, variable=vars_map["smooth_sigma"], orient="horizontal", length=200)
    s_sigma.grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    # value label for smooth_sigma
    val_sigma = ttk.Label(parent, text="")
    val_sigma.grid(row=r, column=3, sticky="w", padx=6)
    _attach_value_label(vars_map["smooth_sigma"], val_sigma, fmt="{:.1f}")
    r += 1

    _make_label("Detection confidence:", r)
    vars_map["confidence"] = tk.DoubleVar(value=settings.confidence)
    s_conf = ttk.Scale(parent, from_=0.0, to=1.0, variable=vars_map["confidence"], orient="horizontal", length=200)
    s_conf.grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    val_conf = ttk.Label(parent, text="")
    val_conf.grid(row=r, column=3, sticky="w", padx=6)
    _attach_value_label(vars_map["confidence"], val_conf, fmt="{:.2f}")
    r += 1

    # Stabilization method + zoom + ybias + max_shift_frac
    _make_label("Stabilization method:", r)
    vars_map["stabilization_method"] = tk.StringVar(value=settings.stabilization_method)
    ttk.OptionMenu(parent, vars_map["stabilization_method"], settings.stabilization_method, "moviepy", "opencv").grid(row=r, column=1, sticky="w", padx=4)
    r += 1

    _make_label("Zoom:", r)
    vars_map["zoom"] = tk.DoubleVar(value=settings.zoom)
    ttk.Scale(parent, from_=1.0, to=1.3, variable=vars_map["zoom"], orient="horizontal", length=200).grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    val_zoom = ttk.Label(parent, text="")
    val_zoom.grid(row=r, column=3, sticky="w", padx=6)
    _attach_value_label(vars_map["zoom"], val_zoom, fmt="{:.3f}")
    r += 1

    _make_label("Vertical bias (ybias):", r)
    vars_map["ybias"] = tk.DoubleVar(value=settings.ybias)
    ttk.Scale(parent, from_=-0.5, to=0.5, variable=vars_map["ybias"], orient="horizontal", length=200).grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    val_ybias = ttk.Label(parent, text="")
    val_ybias.grid(row=r, column=3, sticky="w", padx=6)
    _attach_value_label(vars_map["ybias"], val_ybias, fmt="{:.3f}")
    r += 1

    _make_label("Max shift frac:", r)
    vars_map["max_shift_frac"] = tk.DoubleVar(value=settings.max_shift_frac)
    ttk.Scale(parent, from_=0.0, to=0.5, variable=vars_map["max_shift_frac"], orient="horizontal", length=200).grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    val_maxshift = ttk.Label(parent, text="")
    val_maxshift.grid(row=r, column=3, sticky="w", padx=6)
    _attach_value_label(vars_map["max_shift_frac"], val_maxshift, fmt="{:.3f}")
    r += 1

    # Border mode and reattach audio (for opencv)
    _make_label("Border mode:", r)
    vars_map["border_mode"] = tk.StringVar(value=settings.border_mode)
    ttk.OptionMenu(parent, vars_map["border_mode"], settings.border_mode, "reflect101", "reflect", "replicate", "wrap", "constant").grid(row=r, column=1, sticky="w", padx=4)
    r += 1

    vars_map["reattach_audio"] = tk.BooleanVar(value=settings.reattach_audio)
    ttk.Checkbutton(parent, text="Reattach audio after OpenCV stab", variable=vars_map["reattach_audio"]).grid(row=r, column=0, columnspan=4, sticky="w", padx=4)
    r += 1

    # Split method and reencode fallback
    _make_label("Split method:", r)
    vars_map["split_method"] = tk.StringVar(value=settings.split_method)
    ttk.OptionMenu(parent, vars_map["split_method"], settings.split_method, "ffmpeg", "moviepy").grid(row=r, column=1, sticky="w", padx=4)
    r += 1

    vars_map["reencode_fallback"] = tk.BooleanVar(value=settings.reencode_fallback)
    ttk.Checkbutton(parent, text="Re-encode fallback on split/trim failure", variable=vars_map["reencode_fallback"]).grid(row=r, column=0, columnspan=4, sticky="w", padx=4)
    r += 1

    # Cleanup wide files option
    vars_map["cleanup_wide_files"] = tk.BooleanVar(value=settings.cleanup_wide_files)
    ttk.Checkbutton(parent, text="Remove wide/trimmed intermediate files after successful vertical output", variable=vars_map["cleanup_wide_files"]).grid(row=r, column=0, columnspan=4, sticky="w", padx=4)
    r += 1

    # Temp dir / target resolution
    _make_label("Temp dir:", r)
    vars_map["tmp_dir"] = tk.StringVar(value=settings.tmp_dir or "")
    ttk.Entry(parent, textvariable=vars_map["tmp_dir"], width=36).grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
    def _pick_tmp_dir():
        d = filedialog.askdirectory(title="Select temp directory")
        if d:
            vars_map["tmp_dir"].set(d)
    ttk.Button(parent, text="Browse", command=_pick_tmp_dir).grid(row=r, column=3, sticky="w", padx=4)
    r += 1

    _make_label("Target resolution (W x H):", r)
    vars_map["target_w"] = tk.IntVar(value=settings.target_w)
    vars_map["target_h"] = tk.IntVar(value=settings.target_h)
    ttk.Entry(parent, textvariable=vars_map["target_w"], width=8).grid(row=r, column=1, sticky="w", padx=4)
    ttk.Entry(parent, textvariable=vars_map["target_h"], width=8).grid(row=r, column=2, sticky="w", padx=4)
    r += 1

    # FFmpeg verbose
    vars_map["ffmpeg_verbose"] = tk.BooleanVar(value=settings.ffmpeg_verbose)
    ttk.Checkbutton(parent, text="Show ffmpeg output (debug)", variable=vars_map["ffmpeg_verbose"]).grid(row=r, column=0, columnspan=4, sticky="w", padx=4)
    r += 1

    # Dependency check button
    def _check_deps():
        try:
            import l2s_core
            errs = l2s_core.check_dependencies(verbose=False)
            if not errs:
                messagebox.showinfo("Dependencies", "All optional l2s_core dependencies appear OK.")
            else:
                text = "Missing / failing optional imports:\n\n" + "\n".join([f"{n}: {e}" for n, e in errs])
                text += "\n\nInstall missing packages, e.g.:\n  pip install opencv-python scipy moviepy pillow ultralytics"
                messagebox.showwarning("Dependencies", text)
        except Exception as ex:
            messagebox.showerror("Dependencies", f"Failed to import l2s_core: {ex}")

    ttk.Button(parent, text="Check l2s_core dependencies", command=_check_deps).grid(row=r, column=0, columnspan=4, sticky="we", padx=4, pady=6)
    r += 1

    # Hook to write back current GUI state into a Settings instance
    def writeback_to_settings():
        for k, var in vars_map.items():
            if isinstance(var, (tk.BooleanVar, tk.IntVar, tk.DoubleVar, tk.StringVar)):
                val = var.get()
                if hasattr(settings, k):
                    setattr(settings, k, val)
        # normalize empty tmp_dir to None
        if getattr(settings, "tmp_dir", "") == "":
            settings.tmp_dir = None
        return settings

    # Return controls and writeback helper
    return {"vars": vars_map, "writeback": writeback_to_settings}


# If module executed directly, print a short demo (requires tkinter)
if __name__ == "__main__" and TK_AVAILABLE:
    root = tk.Tk()
    root.title("Long2Short - Settings Demo")
    s = Settings()
    frm = ttk.Frame(root, padding=8)
    frm.pack(fill="both", expand=True)
    controls = add_settings_panel_tk(frm, s, 0)
    def _print_and_quit():
        settings = controls["writeback"]()
        print("Settings chosen:", settings.as_dict())
        root.destroy()
    ttk.Button(frm, text="OK", command=_print_and_quit).pack(fill="x", pady=6)
    root.mainloop()