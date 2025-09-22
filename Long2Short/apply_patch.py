"""
Small convenience script to insert the overlays helper into main.py and call it
to attach overlay_queue metadata into the `result` dict returned by _process_job.

Usage:
  1) Put this script in the same directory as your main.py (Long2Short project root).
  2) Ensure overlays_helper.py (from previous block) is saved in the same directory.
  3) Run: python apply_patch.py

What it does:
  - Creates a timestamped backup of main.py before modifying.
  - Adds: `from overlays_helper import _find_and_attach_overlay_queue_metadata`
    near the top of main.py (if not already present).
  - Finds the body of function `_process_job` and injects a call to:
      result.update(_find_and_attach_overlay_queue_metadata(job_dir, include_content=False))
    immediately before the function's `return result` (the last return inside it).
"""
import os
import re
import shutil
import datetime
import sys

MAIN_PY = "main.py"
BACKUP_SUFFIX = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

def main():
    if not os.path.isfile(MAIN_PY):
        print(f"Error: {MAIN_PY} not found in current directory ({os.getcwd()})")
        sys.exit(1)

    # backup
    bak = f"{MAIN_PY}.bak.{BACKUP_SUFFIX}"
    shutil.copy2(MAIN_PY, bak)
    print(f"Backup created: {bak}")

    with open(MAIN_PY, "r", encoding="utf-8") as f:
        src = f.read()

    modified = src

    # 1) Ensure import of overlays_helper exists
    import_line = "from overlays_helper import _find_and_attach_overlay_queue_metadata"
    if import_line not in modified:
        # attempt to insert after other imports: find first block of imports and append after it
        # As fallback, insert at top.
        pattern = re.compile(r"(^((?:from\s+[^\n]+\n|import\s+[^\n]+\n)+))", re.M)
        m = pattern.search(modified)
        if m:
            insert_at = m.end(1)
            modified = modified[:insert_at] + import_line + "\n" + modified[insert_at:]
            print("Inserted import line after top import block.")
        else:
            modified = import_line + "\n" + modified
            print("Inserted import line at top (no import block detected).")
    else:
        print("Import line already present; skipping import injection.")

    # 2) Inject result.update(...) into _process_job before its last `return result`
    # We'll locate the def _process_job(...) block and then the last 'return result' within it.
    func_pattern = re.compile(r"(def\s+_process_job\s*\(.*?\):)", re.S)
    mfunc = func_pattern.search(modified)
    if not mfunc:
        print("Warning: could not find `def _process_job` in main.py. Please add the call manually.")
        # write backup only, do not overwrite main.py
        return

    # Find where the function body starts (position after the function signature line)
    func_start = mfunc.start()
    # To find the end of the function, search for a top-level 'def ' after the function start
    next_def = re.search(r"\n(?=def\s+\w+\s*\()", modified[mfunc.end():])
    if next_def:
        func_body_region = (mfunc.end(), mfunc.end() + next_def.start())
    else:
        # function likely goes to EOF
        func_body_region = (mfunc.end(), len(modified))

    func_body = modified[func_body_region[0]:func_body_region[1]]

    # find the last occurrence of 'return result' in the function body
    ret_pattern = re.compile(r"return\s+result\s*$", re.M)
    matches = list(ret_pattern.finditer(func_body))
    if not matches:
        print("Warning: could not find `return result` inside _process_job; searching for other return patterns.")
        # try a more permissive search
        matches = list(re.finditer(r"return\s+[\w\.]+\s*$", func_body, re.M))
        if not matches:
            print("No suitable return found. Please insert the call manually into _process_job before returning the response.")
            return

    last_match = matches[-1]
    # compute insertion point (absolute offset)
    insert_offset = func_body_region[0] + last_match.start()

    # prepare insertion text with matching indentation
    # look back to find current line indentation
    line_start = modified.rfind("\n", 0, insert_offset) + 1
    indentation = re.match(r"\s*", modified[line_start:insert_offset]).group(0)
    insert_text = (
        indentation
        + "result.update(_find_and_attach_overlay_queue_metadata(job_dir, include_content=False))\n"
    )

    # only insert if not already present nearby
    nearby_region_start = max(0, insert_offset - 200)
    nearby_region_end = min(len(modified), insert_offset + 200)
    if "_find_and_attach_overlay_queue_metadata" in modified[nearby_region_start:nearby_region_end]:
        print("Appears the metadata attach call is already present near the return; skipping insertion.")
    else:
        modified = modified[:insert_offset] + insert_text + modified[insert_offset:]
        print("Injected result.update(...) into _process_job before last return.")

    # write modified file
    with open(MAIN_PY, "w", encoding="utf-8") as f:
        f.write(modified)
    print(f"Patched {MAIN_PY}. If anything looks off, restore from {bak} and edit manually.")

if __name__ == "__main__":
    main()