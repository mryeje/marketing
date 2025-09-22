#!/usr/bin/env python3
# Debug runner to surface exceptions from l2s_overlays when processing a queue entry.
import json, traceback, sys, os, inspect

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_overlays.py <queue.json>")
        return 1
    qpath = sys.argv[1]
    if not os.path.isfile(qpath):
        print("Queue file not found:", qpath)
        return 2

    print("Queue file:", qpath)
    with open(qpath, "r", encoding="utf-8") as f:
        qj = json.load(f)

    try:
        import l2s_overlays
        print("Imported l2s_overlays OK")
    except Exception:
        print("Failed to import l2s_overlays:")
        traceback.print_exc()
        return 3

    names = sorted([n for n in dir(l2s_overlays) if not n.startswith('_')])
    print("l2s_overlays available names:", names)

    # Try to find a reasonable function to call
    fn = None
    if hasattr(l2s_overlays, "apply_overlays_to_clip"):
        fn = getattr(l2s_overlays, "apply_overlays_to_clip")
        print("Using apply_overlays_to_clip")
    elif hasattr(l2s_overlays, "process_overlay_entry"):
        fn = getattr(l2s_overlays, "process_overlay_entry")
        print("Using process_overlay_entry")
    else:
        print("No obvious overlay function found. Paste the module name list above and I'll advise next.")
        return 4

    try:
        print("Function signature:", inspect.signature(fn))
    except Exception:
        pass

    entries = qj.get("entries", [])
    if not entries:
        print("Queue contains no entries.")
        return 0

    for entry in entries:
        print("\n--- Debugging queue entry id:", entry.get("id", "<no-id>"))
        print("out_path:", entry.get("out_path"))
        print("overlay_instructions keys:", list(entry.get("overlay_instructions", {}).keys()) if isinstance(entry.get("overlay_instructions"), dict) else type(entry.get("overlay_instructions")))
        print("srt_for_clip length:", len(entry.get("srt_for_clip", [])) if entry.get("srt_for_clip") is not None else 0)
        # Try calling the function using a few common signatures and print any traceback
        tried = []
        def try_call(callable_fn, *a, **kw):
            print(f"\nAttempting call: {callable_fn.__name__} args={a} kwargs={list(kw.keys())}")
            try:
                res = callable_fn(*a, **kw)
                print("Call completed. Return value type:", type(res))
                return None
            except Exception:
                print("Exception raised:")
                traceback.print_exc()
                return sys.exc_info()

        # Common signature 1: (out_path, overlay_instructions, srt_stub)
        try_call(fn, entry.get("out_path"), entry.get("overlay_instructions"), entry.get("srt_for_clip", []))
        # Common signature 2: (entry_dict)
        try_call(fn, entry)
        # Common signature 3: named args
        try_call(fn, **{"out_path": entry.get("out_path"), "overlay_instructions": entry.get("overlay_instructions"), "srt_stub": entry.get("srt_for_clip", [])})

    print("\nDebug run complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())