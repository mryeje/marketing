import importlib, sys, traceback, os

print("importlib.__file__ =", getattr(importlib, "__file__", None))
print("importlib.__path__ =", list(getattr(importlib, "__path__", [])))

paths = list(getattr(importlib, "__path__", []))
if paths:
    p0 = paths[0]
    print("\nListing files in:", p0)
    try:
        for n in sorted(os.listdir(p0)):
            fn = os.path.join(p0, n)
            info = []
            try:
                info.append(str(os.path.getsize(fn)))
            except Exception:
                pass
            print(n, " ".join(info))
    except Exception as e:
        print("Error listing directory:", e)

print("\nCheck specifically for importlib/util.py existence:")
if paths:
    util_path = os.path.join(paths[0], "util.py")
    print(util_path, "exists?", os.path.exists(util_path))
    if os.path.exists(util_path):
        try:
            with open(util_path, "r", encoding="utf-8") as f:
                sample = f.read(400)
            print("\nFirst 400 chars of util.py:\n", sample)
        except Exception as e:
            print("Could not read util.py:", e)

print("\nAttempting to import importlib.util and show traceback if it fails:")
try:
    import importlib.util as util
    print("importlib.util loaded OK, util.__file__ =", getattr(util, "__file__", None))
except Exception:
    traceback.print_exc()