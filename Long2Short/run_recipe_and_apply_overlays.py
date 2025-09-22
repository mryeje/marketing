#!/usr/bin/env python3
"""
Run process_recipe for a recipe, then run overlays on the queue produced.

Usage (Windows cmd.exe):
  cd "C:/Users/mryej/Documents/Python/Marketing tools/Long2Short"
  python run_recipe_and_apply_overlays.py "C:/Users/mryej/Documents/Python/Marketing tools/clips/sharpening-recipe.json"

This script will:
 - call l2s_core.process_recipe(recipe, args) with reasonable defaults,
 - locate the most recent overlays_queue_*.json created in the recipe's directory,
 - run l2s_overlays.process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=True)
 - print results and any errors.
"""
import sys
import os
import types
import traceback
from pathlib import Path
import time
import glob
import json

if len(sys.argv) < 2:
    print("Usage: python run_recipe_and_apply_overlays.py <path-to-recipe.json>")
    sys.exit(2)

recipe_path = os.path.abspath(sys.argv[1])
if not os.path.isfile(recipe_path):
    print("Recipe file not found:", recipe_path)
    sys.exit(3)

# Build args namespace consistent with l2s_core expectations
args = types.SimpleNamespace()
args.device = "auto"
args.prefer_pillow = True
args.model = None
args.confidence = 0.25
args.zoom = 1.05
args.ybias = 0.10
args.max_shift_frac = 0.25
args.TARGET_W = 1080
args.TARGET_H = 1920
args.border_mode = "reflect101"

try:
    import l2s_core
except Exception:
    print("Failed to import l2s_core. Traceback:")
    traceback.print_exc()
    sys.exit(4)

print("Running l2s_core.process_recipe on:", recipe_path)
try:
    res = l2s_core.process_recipe(recipe_path, args)
    print("process_recipe completed. Summary:")
    print(json.dumps(res, indent=2))
except Exception:
    print("process_recipe raised an exception:")
    traceback.print_exc()
    sys.exit(5)

# find the most recent overlays_queue file in the recipe directory (same dir as recipe)
recipe_dir = os.path.dirname(recipe_path) or os.getcwd()
pattern = os.path.join(recipe_dir, "overlays_queue_*.json")
queues = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
if not queues:
    print("No overlays_queue_*.json found in recipe directory:", recipe_dir)
    print("Listing files in directory:")
    for p in sorted(os.listdir(recipe_dir)):
        print(" ", p)
    sys.exit(0)

queue_path = queues[0]
print("Found overlays queue:", queue_path)
# print a short preview
try:
    with open(queue_path, "r", encoding="utf-8") as f:
        qd = json.load(f)
    print("  entries:", len(qd.get("entries", [])))
    if qd.get("entries"):
        print("  first entry keys:", list(qd.get("entries")[0].keys()))
except Exception:
    print("  (could not open queue preview)")

# Run overlays processor
try:
    import l2s_overlays
except Exception:
    print("Failed to import l2s_overlays. Traceback:")
    traceback.print_exc()
    sys.exit(6)

print("Running l2s_overlays.process_overlays_queue on:", queue_path)
try:
    failures = l2s_overlays.process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=True)
    print("process_overlays_queue returned:", failures)
    if failures:
        print("Failures detail:", json.dumps(failures, indent=2))
except Exception:
    print("Exception while running process_overlays_queue:")
    traceback.print_exc()
    sys.exit(7)

print("Done.")