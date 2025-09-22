# Prints the first overlay_instructions object from the overlays queue JSON.
import json, sys, os

queue_path = r"C:\Users\mryej\Documents\Python\Marketing tools\clips\overlays_queue_sharpening-recipe_1758178076.json"
if not os.path.isfile(queue_path):
    print("Queue file not found:", queue_path)
    sys.exit(2)

with open(queue_path, "r", encoding="utf-8") as f:
    qd = json.load(f)

entries = qd.get("entries", [])
if not entries:
    print("No entries in queue:", queue_path)
    sys.exit(0)

entry0 = entries[0]
ov = entry0.get("overlay_instructions", {})
print("=== overlay_instructions (first entry) ===")
print(json.dumps(ov, ensure_ascii=False, indent=2))
# Also print the full queue entry for context
print("\n=== full first queue entry ===")
print(json.dumps(entry0, ensure_ascii=False, indent=2))