import os, sys

patterns = [
    'def apply_overlays_to_clip',
    'def apply_overlays',
    'def apply_overlay',
    'def draw_overlay',
    'def make_frame',
    'def typewriter',
    'overlay_text',
]

this_file = os.path.basename(__file__)
found = False

for root, _, files in os.walk('.'):
    for f in files:
        if not f.endswith('.py'):
            continue
        if f == this_file:
            continue
        p = os.path.join(root, f)
        try:
            s = open(p, encoding='utf-8').read()
        except Exception:
            continue
        for pat in patterns:
            idx = s.find(pat)
            if idx != -1:
                found = True
                print('FILE:', p)
                print('-' * 80)
                start = max(0, idx - 200)
                print(s[start:idx+4000])
                print('\n' + '='*120 + '\n')
                break
if not found:
    print('NOT_FOUND')