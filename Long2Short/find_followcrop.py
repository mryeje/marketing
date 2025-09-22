# Finds likely follow-crop / stabilizer call sites by text search (no imports)
import os, re, sys

root = os.getcwd()
patterns = [
    r'Producing vertical follow-crop',
    r'Follow-crop failed',
    r'follow-crop',
    r'follow_crop',
    r'stabiliz',           # matches stabilize/stabilise
    r'stabilize_and_crop',
    r'method\s*=',
    r'opencv',
    r'follow',
]

py_files = []
for dirpath, dirnames, filenames in os.walk(root):
    # skip common virtualenv / .git dirs
    if any(part.startswith('.') or part in ('venv','env','__pycache__') for part in dirpath.split(os.sep)):
        continue
    for fn in filenames:
        if fn.endswith('.py'):
            py_files.append(os.path.join(dirpath, fn))

def search_file(path):
    out = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return out
    for i, line in enumerate(lines):
        for pat in patterns:
            if re.search(pat, line, re.IGNORECASE):
                # capture context lines
                start = max(0, i-3)
                end = min(len(lines), i+3)
                ctx = ''.join(lines[start:end])
                out.append((i+1, pat, line.rstrip('\n'), ctx))
                break
    return out

results = []
for p in sorted(py_files):
    matches = search_file(p)
    if matches:
        results.append((p, matches))

if not results:
    print("No matches found for follow-crop/stabilizer patterns in .py files (searched %d files)." % len(py_files))
    sys.exit(0)

for path, matches in results:
    print("="*80)
    print("FILE:", path)
    for lineno, pat, line, ctx in matches:
        print("--- match pattern:", pat, "line:", lineno)
        print(line)
        print("context:")
        for cl in ctx.splitlines():
            print("  ", cl)
    print()