import sys, os
p = "l2s_overlays.py"
if not os.path.isfile(p):
    print("ERROR: file not found:", p)
    sys.exit(1)
s = open(p, encoding="utf-8").read()
idx = s.find("def apply_overlays_to_clip")
if idx == -1:
    print("NOT_FOUND")
    sys.exit(1)
print("FILE:", p)
print("-" * 80)
print(s[idx:idx+120000])