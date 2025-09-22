# import_check.py
import importlib, traceback, sys
try:
    m = importlib.import_module('l2s_overlays')
    print('IMPORTED:', getattr(m, '__file__', '<unknown>'))
    print('HAS process_overlays_queue:', hasattr(m, 'process_overlays_queue'))
    if hasattr(m, 'process_overlays_queue'):
        import inspect
        print('process_overlays_queue defined at:', inspect.getsource(m.process_overlays_queue).splitlines()[0])
except Exception:
    traceback.print_exc()
    sys.exit(1)