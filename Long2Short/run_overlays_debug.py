#!/usr/bin/env python3
"""
Run overlays processor with extra diagnostics and capture errors.

Usage:
  python run_overlays_debug.py

Must be run with the same Python environment you use for Long2Short/GUI.
"""
import glob, json, os, sys, traceback, datetime, subprocess, importlib

# Adjust this folder if your overlays_queue files are in a different directory
QUEUEDIR = os.path.join(os.path.dirname(__file__), "..", "clips")
QUEUEDIR = os.path.normpath(QUEUEDIR)

def find_latest_queue():
    pattern = os.path.join(QUEUEDIR, "overlays_queue_*.json")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None

def tail_file(path, lines=20):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            size = 1024
            data = b""
            while end > 0 and len(data.splitlines()) <= lines:
                start = max(0, end - size)
                f.seek(start)
                data = f.read(end - start) + data
                end = start
                size *= 2
            return b"\n".join(data.splitlines()[-lines:]).decode("utf-8", errors="replace")
    except Exception:
        return None

def main():
    q = find_latest_queue()
    if not q:
        print("No overlays_queue_*.json found in:", QUEUEDIR)
        sys.exit(1)
    print("Using queue:", q)
    try:
        jd = json.load(open(q, "r", encoding="utf-8"))
    except Exception as e:
        print("Failed to load queue JSON:", e)
        sys.exit(2)

    entries = jd.get("entries", [])
    print(f"Queue entries: {len(entries)}")
    if entries:
        e0 = entries[0]
        oi = e0.get("overlay_instructions", {})
        print("First entry id:", e0.get("id"))
        print(" overlay_instructions top-level keys:", list(oi.keys()))
        print(" top-level effect/effects:", oi.get("effect"), oi.get("effects"))
        ot0 = (oi.get("overlay_text") or [None])[0]
        print(" overlay_text[0]:", ot0)
    dbg_log = os.path.join(os.path.dirname(q), "overlays_debug.log")
    if os.path.isfile(dbg_log):
        print("\n--- last lines of overlays_debug.log ---")
        print(tail_file(dbg_log, lines=30) or "(empty)")
    else:
        print("\nNo overlays_debug.log found at", dbg_log)

    # Try to import l2s_overlays and call its process function if available.
    try:
        m = importlib.import_module("l2s_overlays")
        print("\nImported l2s_overlays from:", getattr(m, "__file__", "<unknown>"))
        if hasattr(m, "process_overlays_queue"):
            print("Calling process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=True)...")
            try:
                res = m.process_overlays_queue(q, dry_run=False, parallel=1, keep_temp=True)
                print("process_overlays_queue returned:", res)
                print("Done.")
                return
            except Exception:
                tb = traceback.format_exc()
                print("\nprocess_overlays_queue raised an exception; writing overlays_error.log")
                err_path = os.path.join(os.path.dirname(q), "overlays_error.log")
                with open(err_path, "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.datetime.utcnow().isoformat()}Z ---\n")
                    f.write(tb + "\n")
                print(tb)
                print("\nFull traceback written to:", err_path)
                return
        else:
            print("l2s_overlays module does not expose process_overlays_queue. Will attempt to run l2s_overlays.py as a script.")
    except Exception as ex:
        print("Importing l2s_overlays failed:", ex)
        print("Will attempt to run l2s_overlays.py as a subprocess if available.")

    # Fallback: try to find l2s_overlays.py next to this script and run it
    overlays_script = os.path.join(os.path.dirname(__file__), "l2s_overlays.py")
    if not os.path.isfile(overlays_script):
        overlays_script = None
    if overlays_script:
        cmd = [sys.executable, overlays_script, "--queue", q, "--keep-temp", "--parallel", "1"]
        print("\nRunning overlays script subprocess:", " ".join(cmd))
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, encoding="utf-8")
            out = p.stdout or ""
            print("\n--- overlays subprocess output ---\n")
            print(out)
            if p.returncode != 0:
                err_path = os.path.join(os.path.dirname(q), "overlays_error.log")
                with open(err_path, "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.datetime.utcnow().isoformat()}Z subprocess returncode={p.returncode} ---\n")
                    f.write(out + "\n")
                print("\nSubprocess returned non-zero. Full output saved to:", err_path)
            return
        except Exception as ex:
            print("Failed to run overlays subprocess:", ex)
            return

    print("Could not run overlays processor (no module function and no script found).")

if __name__ == "__main__":
    main()