#!/usr/bin/env python3
"""
Generate a requirements.txt from a Python environment.

Usage:
  # Run using the active interpreter (recommended if you are in the venv)
  python generate_requirements.py --output requirements.txt

  # Or target a specific python executable (no need to activate that venv)
  python generate_requirements.py --target-python "C:\path\to\python.exe" --output requirements.txt

Options:
  --target-python PATH    Run pip freeze using this Python executable (optional).
  --output PATH           Output file path (default: requirements.txt).
  --exclude NAMES         Comma-separated package names to exclude (default: pip,setuptools,wheel).
  --annotate              Add a header with timestamp and interpreter path.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def run_pip_freeze(python_exe: str):
    cmd = [python_exe, "-m", "pip", "freeze"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"pip freeze failed ({proc.returncode}):\n{proc.stderr.strip()}")
    return proc.stdout.splitlines()

def filter_lines(lines, exclude):
    if not exclude:
        return lines
    ex = set(n.strip().lower() for n in exclude)
    out = []
    for ln in lines:
        # keep editable installs and VCS links
        if ln.strip().startswith("-e ") or ln.strip().startswith("git+") or ln.strip().startswith("http"):
            out.append(ln)
            continue
        # normal pinned form: package==1.2.3 or package>=...
        name = ln.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0].strip().lower()
        if name and name not in ex:
            out.append(ln)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-python", default=None, help="Path to python executable to run pip freeze with")
    ap.add_argument("--output", default="requirements.txt", help="Output file path")
    ap.add_argument("--exclude", default="pip,setuptools,wheel", help="Comma-separated package names to exclude")
    ap.add_argument("--annotate", action="store_true", help="Add header with timestamp and interpreter path")
    args = ap.parse_args()

    python_exe = args.target_python or sys.executable

    try:
        lines = run_pip_freeze(python_exe)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    excludes = [s for s in (args.exclude or "").split(",") if s.strip()]
    lines = filter_lines(lines, excludes)

    out_path = Path(args.output)
    header_lines = []
    if args.annotate:
        header_lines = [
            f"# requirements.txt generated: {datetime.utcnow().isoformat()}Z",
            f"# interpreter: {python_exe}",
            "# excluded: " + ",".join(excludes) if excludes else "# excluded: none",
            ""
        ]
    out_text = "\n".join(header_lines + lines) + ("\n" if not out_path.exists() or out_path.is_file() else "")
    out_path.write_text(out_text, encoding="utf-8")
    print(f"Wrote {len(lines)} entries to {out_path.resolve()} using {python_exe}")

if __name__ == "__main__":
    main()