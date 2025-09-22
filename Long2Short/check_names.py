#!/usr/bin/env python3
import traceback, sys

def main():
    try:
        import l2s_core
    except Exception as e:
        print("[ERROR] Importing l2s_core failed:")
        traceback.print_exc()
        return

    print("l2s_core module file:", getattr(l2s_core, "__file__", "<unknown>"))
    print("has extract_targets:", hasattr(l2s_core, "extract_targets"))
    print("has extract_targets_framewise:", hasattr(l2s_core, "extract_targets_framewise"))
    print("has stabilize_and_crop:", hasattr(l2s_core, "stabilize_and_crop"))
    print("has stabilize_and_crop_opencv:", hasattr(l2s_core, "stabilize_and_crop_opencv"))

if __name__ == '__main__':
    main()