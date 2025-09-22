# diag_font.py
import os, sys
from pathlib import Path
try:
    import PIL
    from PIL import ImageFont, Image
    from PIL import features
except Exception as e:
    print("PIL import failed:", e)
    sys.exit(0)

print("Pillow version:", getattr(PIL, "__version__", "unknown"))
print("Pillow freetype feature:", features.check("freetype"))
print("Pillow fontconfig feature:", features.check("fontconfig"))

fonts_dir = r"C:\Windows\Fonts"
print("Fonts dir exists:", os.path.isdir(fonts_dir))
candidates = []
for root, _, files in os.walk(fonts_dir):
    for fn in files:
        if "dejavu" in fn.lower() or "dejavusans" in fn.lower():
            candidates.append(os.path.join(root, fn))
print("DejaVu files found in Windows fonts dir:", len(candidates))
for p in candidates:
    try:
        st = os.stat(p)
        print(" -", p, "size=", st.st_size, "readable=", os.access(p, os.R_OK))
        # try to open file bytes
        with open(p, "rb") as fh:
            print("   first bytes:", fh.read(16)[:16])
    except Exception as e:
        print("   cannot stat/read:", e)

# Try loading by filename and by full path
test_names = ["DejaVuSans.ttf", "DejaVuSans", r"C:\Windows\Fonts\DejaVuSans.ttf"]
for name in test_names:
    try:
        f = ImageFont.truetype(name, size=72)
        print("ImageFont.truetype succeeded for:", name)
    except Exception as e:
        print("ImageFont.truetype FAILED for:", name, "->", e)

# As fallback, list a few font files to test if any truetype loads
loaded_any = False
count = 0
for root, _, files in os.walk(fonts_dir):
    for fn in files:
        if fn.lower().endswith((".ttf", ".otf", ".ttc")):
            p = os.path.join(root, fn)
            try:
                ImageFont.truetype(p, size=48)
                print("Can load font file:", p)
                loaded_any = True
                count += 1
            except Exception:
                pass
            if count >= 3:
                break
    if count >= 3:
        break
print("Could load any system TTF:", loaded_any)