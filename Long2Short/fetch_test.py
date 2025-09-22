import requests, sys, traceback
print("python:", sys.executable)
try:
    r = requests.get("https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4", stream=True, timeout=15)
    print("status:", r.status_code)
    print("content-type:", r.headers.get("content-type"))
    print("content-length:", r.headers.get("content-length"))
except Exception:
    traceback.print_exc()
    sys.exit(1)