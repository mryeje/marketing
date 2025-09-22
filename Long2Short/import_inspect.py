import importlib, inspect, sys, os, traceback
try:
    m = importlib.import_module('l2s_overlays')
    print('IMPORTED MODULE:', getattr(m, '__file__', '<unknown>'))
    names = sorted([n for n in dir(m) if 'process' in n])
    print('module names containing "process":', names)
    print('HAS process_overlays_queue attribute:', hasattr(m, 'process_overlays_queue'))
except Exception:
    print('IMPORT ERROR:')
    traceback.print_exc()
    sys.exit(1)

src_path = os.path.abspath(m.__file__)
print('SOURCE FILE:', src_path)
try:
    src = open(src_path, encoding='utf-8').read()
except Exception as e:
    print('FAILED TO READ SOURCE:', e)
    sys.exit(1)

found = 'def process_overlays_queue' in src
print("literal 'def process_overlays_queue' present in file:", found)
if found:
    idx = src.find('def process_overlays_queue')
    print('source index:', idx)
    print('--- snippet (400 chars starting at def) ---')
    print(src[idx: idx+400])
    print('--- end snippet ---')

print('--- file tail (last ~1200 chars) ---')
tail = src[-1200:] if len(src) > 1200 else src
print(tail)
print('--- end file tail ---')