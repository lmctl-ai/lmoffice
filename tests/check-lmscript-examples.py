#!/usr/bin/env python3
"""Check every public gallery script with the pinned lmscript compiler."""
import os
from pathlib import Path
import subprocess
import sys

compiler=os.environ.get("LMSCRIPT_BIN") or sys.argv[1]
root=Path(__file__).resolve().parents[1]
files=sorted((root/"examples").rglob("*.lms"))
if len(files)!=90: raise SystemExit(f"expected 90 public examples, found {len(files)}")
for example in files:
 command=[compiler,"--check",str(example)]
 if os.name=="nt" and compiler.lower().endswith((".cmd",".bat")):
  command=["cmd.exe","/d","/s","/c",subprocess.list2cmdline(command)]
 result=subprocess.run(command,cwd=root)
 if result.returncode: raise SystemExit(f"lmscript --check failed: {example}")
print(f"PASS lmscript --check: {len(files)} public examples")
