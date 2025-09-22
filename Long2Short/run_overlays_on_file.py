# Run l2s_overlays.process_overlays_queue on a specific queue file with full traceback.
import sys, os, traceback

if len(sys.argv) < 2:
    print("Usage: python run_overlays_on_file.py <path-to-overlays_queue.json>")
    sys.exit(2)

queue_path = sys.argv[1]
if not os.path.isfile(queue_path):
    print("Queue file not found:", queue_path)
    sys.exit(3)

print("Running l2s_overlays.process_overlays_queue on:", queue_path)
try:
    import l2s_overlays
except Exception:
    print("Failed to import l2s_overlays:")
    traceback.print_exc()
    sys.exit(4)

try:
    # keep_temp=True so intermediary artifacts remain for debugging; run single-threaded
    failures = l2s_overlays.process_overlays_queue(queue_path, dry_run=False, parallel=1, keep_temp=True)
    print("process_overlays_queue returned:", failures)
except Exception:
    print("Exception while running process_overlays_queue:")
    traceback.print_exc()
    sys.exit(5)