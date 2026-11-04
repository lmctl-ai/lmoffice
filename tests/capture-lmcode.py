#!/usr/bin/env python3
"""Capture one compiler-emitted program into a private integration-test fixture."""
from pathlib import Path
import os
import shutil
import sys

if len(sys.argv) != 4 or sys.argv[2] != "--lmcode":
    raise SystemExit("expected OUTPUT --lmcode PROGRAM")
source, target = Path(sys.argv[3]), Path(sys.argv[1])
shutil.copyfile(source, target)
if source.read_bytes()[:6] != b"DSLB\x00\x06":
    raise SystemExit("compiler did not emit lmcode bytecode version 6")
if os.name == "nt":
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
sys.stdout.buffer.write(b'LMCODE_RETURN_BEGIN\n{"ok":true,"result":null}\nLMCODE_RETURN_END\n')
sys.stdout.buffer.flush()
