# helpers to load presets (JSON/YAML) and integrate them into the existing Tk GUI settings panel
# Usage:
#   presets = load_presets("presets.json")
#   add_presets_ui(parent_frame, presets, settings_obj, settings_controls)
#
# settings_controls is the dict returned by add_settings_panel_tk(...),
# which contains "vars" and "writeback".

import json
import yaml
import os
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None

def load_presets(path):
    """
    Load presets from JSON or YAML file.
    Returns a dict mapping preset name -> preset dict {description, settings}
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    _, ext = os.path.splitext(path.lower())
    with open(path, "r", encoding="utf-8") as f:
        if ext in (".yaml", ".yml"):
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    presets = {}
    items = data.get("presets") if isinstance(data, dict) and "presets" in data else data
    for p in items:
        name = p.get("name") if isinstance(p, dict) else None
        if not name:
            continue
        presets[name] = {"description": p.get("description", ""), "settings": p.get("settings", p.get("values", {}))}
    return presets

def add_presets_ui(parent, presets: dict, settings_obj, settings_controls, row=0):
    """
    Add a compact presets dropdown + apply/import/export buttons into the parent Tk container.
    - parent: tk.Frame where controls will be placed
    - presets: dict returned by load_presets()
    - settings_obj: the Settings instance used by the GUI
    - settings_controls: dict returned by add_settings_panel_tk() containing "vars" and "writeback"
    Returns a small dict with UI vars and apply function.
    """
    if tk is None:
        raise RuntimeError("Tkinter not available")

    vars_map = settings_controls.get("vars", {})
    writeback = settings_controls.get("writeback")

    preset_names = list(presets.keys())
    if not preset_names:
        lbl = ttk.Label(parent, text="No presets loaded")
        lbl.grid(row=row, column=0, sticky="w")
        return {"var": None, "apply": lambda name=None: None}

    sel_var = tk.StringVar(value=preset_names[0])
    ttk.Label(parent, text="Presets:").grid(row=row, column=0, sticky="w", padx=4)
    menu = ttk.OptionMenu(parent, sel_var, preset_names[0], *preset_names)
    menu.grid(row=row, column=1, sticky="w", padx=4)

    def apply_preset(name=None):
        nm = name or sel_var.get()
        preset = presets.get(nm)
        if not preset:
            return
        values = preset.get("settings", {})
        # write into UI-bound variables where available, else set attribute on settings_obj
        for k, v in values.items():
            if k in vars_map:
                var = vars_map[k]
                # Convert booleans and numbers sensibly
                try:
                    # If the control is a tk.Variable subclass, call set with the appropriate type
                    if isinstance(var, (tk.BooleanVar, tk.IntVar, tk.DoubleVar, tk.StringVar)):
                        var.set(v)
                    else:
                        # fallback: try to set attribute on settings_obj
                        setattr(settings_obj, k, v)
                except Exception:
                    setattr(settings_obj, k, v)
            else:
                try:
                    setattr(settings_obj, k, v)
                except Exception:
                    pass
        # ensure settings_obj receives the latest UI values via writeback (if provided)
        if callable(writeback):
            try:
                writeback()
            except Exception:
                pass

    apply_btn = ttk.Button(parent, text="Apply preset", command=lambda: apply_preset(None))
    apply_btn.grid(row=row, column=2, padx=6, sticky="w")

    def import_presets_dialog():
        p = filedialog.askopenfilename(title="Import presets", filetypes=[("JSON/YAML", "*.json *.yaml *.yml"), ("All files", "*.*")])
        if not p:
            return
        try:
            new = load_presets(p)
            presets.clear()
            presets.update(new)
            # update option menu choices
            menu['menu'].delete(0, 'end')
            for name in presets.keys():
                menu['menu'].add_command(label=name, command=tk._setit(sel_var, name))
            sel_var.set(next(iter(presets.keys())))
            messagebox.showinfo("Presets", f"Imported {len(presets)} presets from {os.path.basename(p)}")
        except Exception as e:
            messagebox.showerror("Import presets", f"Failed to import: {e}")

    def export_presets_dialog():
        p = filedialog.asksaveasfilename(title="Export presets", defaultextension=".json", filetypes=[("JSON", "*.json"), ("YAML", "*.yaml *.yml")])
        if not p:
            return
        # write in JSON by default
        try:
            out = {"presets": []}
            for name, data in presets.items():
                out["presets"].append({"name": name, "description": data.get("description", ""), "settings": data.get("settings", {})})
            if p.lower().endswith((".yaml", ".yml")):
                with open(p, "w", encoding="utf-8") as f:
                    yaml.safe_dump(out, f, sort_keys=False)
            else:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(out, f, indent=2)
            messagebox.showinfo("Presets", f"Exported presets to {p}")
        except Exception as e:
            messagebox.showerror("Export presets", f"Failed to export: {e}")

    ttk.Button(parent, text="Import...", command=import_presets_dialog).grid(row=row+1, column=0, sticky="w", padx=4, pady=2)
    ttk.Button(parent, text="Export...", command=export_presets_dialog).grid(row=row+1, column=1, sticky="w", padx=4, pady=2)

    return {"var": sel_var, "apply": apply_preset, "menu": menu, "presets": presets}

# Example integration snippet (to drop into your GUI after add_settings_panel_tk(...) is called):
#
# presets = load_presets("presets.json")                  # or "presets.yaml"
# presets_ui = add_presets_ui(settings_frame, presets, settings, settings_controls, row=20)
# # When starting a job you can enforce a preset programmatically:
# presets_ui["apply"]("Quality / Smooth")
#
# The add_presets_ui call will add dropdown + Apply/Import/Export buttons to the settings_frame.