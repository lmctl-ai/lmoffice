#!/usr/bin/env python3
"""Credential-free native job integrity check against trusted job outputs."""
import sys
from pathlib import Path
from release_policy import digest,validate_files
root=Path(sys.argv[1]);expected=sys.argv[2]
if digest((root/'SHA256SUMS').read_bytes())!=expected:raise SystemExit('candidate checksum identity changed in the artifact handoff')
validate_files(root);print('Native candidate bytes match the verified handoff')
