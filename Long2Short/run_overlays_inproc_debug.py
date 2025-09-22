#!/usr/bin/env python3
"""
Run l2s_overlays.process_overlays_queue(...) in-process and capture full stdout/stderr
and any exception traceback to the console and into overlays_error.log next to the queue file.

Usage:
  python run_overlays_inproc_debug.py "C:\\path\\to\\overlays_queue_xxx.json"
or
  python run_overlays_inproc_debug.py
  (will auto-find the newest overlays_queue_*.json in ../clips)
"""
import sys, os, glob, importlib, io, traceback, datetime, contextlib, json

def find_latest_queue():
    # default clips dir relative to this script (adjust if your layout differs)
    base = os.path.dirname(os.path.abspath(__file__))
    clips_dir = os.path.normpath(os.path.join(base, "..", "clips"))
    pattern = os.path.join(clips_dir, "overlays_queue_*.json")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None

def main():
    if len(sys.argv) > 1:
        q = sys.argv[1]
        if not os.path.isfile(q):
            print("Queue path not found:", q)
            sys.exit(2)
    else:
        q = find_latest_queue()
        if not q:
            print("No overlays_queue_*.json found in expected clips folder.")
            sys.exit(3)

    q = os.path.abspath(q)
    qdir = os.path.dirname(q)
    print("Using queue:", q)
    try:
        jd = json.load(open(q, "r", encoding="utf-8"))
        print("Queue entries:", len(jd.get("entries", [])))
    except Exception as e:
        print("Failed to read queue JSON:", e)

    # import overlays module
    try:
        m = importlib.import_module("l2s_overlays")
        print("Imported l2s_overlays from:", getattr(m, "__file__", "<unknown>"))
    except Exception as e:
        print("Failed to import l2s_overlays:", e)
        traceback.print_exc()
        sys.exit(4)

    buf = io.StringIO()
    result = None
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            # call processor with common params (adjust if your code expects different signature)
            if hasattr(m, "process_overlays_queue"):
                result = m.process_overlays_queue(q, dry_run=False, parallel=1, keep_temp=True)
            else:
                raise RuntimeError("l2s_overlays module has no process_overlays_queue function")
    except Exception:
        tb = traceback.format_exc()
        captured = buf.getvalue() + "\n\n=== exception traceback ===\n" + tb
        # write overlays_error.log with timestamp
        err_path = os.path.join(qdir, "overlays_error.log")
        try:
            with open(err_path, "a", encoding="utf-8") as f:
                f.write("\n--- " + datetime.datetime.utcnow().isoformat() + "Z ---\n")
                f.write(captured + "\n")
            print("Exception occurred. Full capture written to:", err_path)
        except Exception as e2:
            print("Failed to write overlays_error.log:", e2)
        # also print captured to console
        print(captured)
        sys.exit(1)

    # no exception - print full captured output and returned value
    captured = buf.getvalue()
    print("=== overlays run captured output ===\n")
    print(captured)
    print("\n=== process_overlays_queue returned ===")
    print(repr(result))
    # also write successful run capture to overlays_error.log for inspection
    try:
        out_path = os.path.join(qdir, "overlays_error.log")
        with open(out_path, "a", encoding="utf-8") as f:
            f.write("\n--- " + datetime.datetime.utcnow().isoformat() + "Z successful run ---\n")
            f.write(captured + "\n")
            f.write("RETURN: " + repr(result) + "\n")
        print("Run capture appended to:", out_path)
    except Exception:
        pass

if __name__ == "__main__":
    main()