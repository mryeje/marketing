import json
from pathlib import Path
import sys

def main(path):
    p = Path(path)
    if not p.exists():
        print("File not found:", p)
        return 1
    data = json.loads(p.read_text(encoding="utf-8"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    path = r"C:\Users\mryej\AppData\Local\Temp\tmpyiq_xggf_overlay_queue.json"
    if len(sys.argv) > 1:
        path = sys.argv[1]
    sys.exit(main(path))