# Runs l2s_overlays.process_overlays_queue with full traceback and leaves temporary files.
# This prints any exception trace the overlays module raises.
import traceback, json, sys, os

queue_path = r"C:\Users\mryej\Documents\Python\Marketing tools\clips\overlays_queue_sharpening-recipe_1758178076.json"
if not os.path.isfile(queue_path):
    print("Queue file not found:", queue_path)
    sys.exit(2)

print("Running l2s_overlays.process_overlays_queue on:", queue_path)
try:
    import l2s_overlays
except Exception:
    print("Failed to import l2s_overlays:")
    traceback.print_exc()
    sys.exit(1)

try:
    # keep_temp=True so intermediary artifacts remain for debugging, parallel=1 to run single-threaded
    failures = l2s_overlays.process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=True)
    print("process_overlays_queue returned failures count:", failures)
except Exception:
    print("Exception while running process_overlays_queue:")
    traceback.print_exc()
    sys.exit(1)