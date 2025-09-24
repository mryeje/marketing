import importlib.util, traceback, sys
spec = importlib.util.spec_from_file_location("mod", "L2S_server.py")
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("Loaded module; app present?", hasattr(mod, "app"))
except Exception:
    traceback.print_exc()
    sys.exit(1)