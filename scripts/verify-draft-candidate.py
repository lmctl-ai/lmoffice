#!/usr/bin/env python3
"""Verify a repository_dispatch draft tag, manifest, and sealed assets."""
import hashlib
import json
from pathlib import Path
import re
import sys

if len(sys.argv)!=4: raise SystemExit("usage: verify-draft-candidate.py TAG SHA256SUMS_SHA256 DIRECTORY")
tag,expected,folder=sys.argv[1:]
root=Path(folder)
if not re.fullmatch(r"v\d+\.\d+\.\d+",tag): raise SystemExit("dispatch tag is not a stable version tag")
if not re.fullmatch(r"[0-9a-f]{64}",expected): raise SystemExit("dispatch SHA256SUMS digest is malformed")
sums=root/"SHA256SUMS"
if hashlib.sha256(sums.read_bytes()).hexdigest()!=expected: raise SystemExit("draft SHA256SUMS differs from repository_dispatch identity")
manifest=json.loads((root/"RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
version=tag[1:]
if manifest.get("format")!="lmoffice-release-candidate/1" or manifest.get("repository")!="lmctl-ai/lmoffice": raise SystemExit("unsupported candidate manifest")
if manifest.get("tag")!=tag or manifest.get("version")!=version: raise SystemExit("candidate manifest tag/version mismatch")
if not re.fullmatch(r"[0-9a-f]{40}",str(manifest.get("source_sha",""))): raise SystemExit("candidate source commit is invalid")
required={"lmoffice-linux-x64","lmoffice-linux-arm64","lmoffice-macos-arm64","lmoffice-macos-x64","lmoffice-windows-x64.exe","LICENSE","THIRD_PARTY_NOTICES.md","RELEASE-MANIFEST.json"}
if set(manifest.get("assets",[]))!=required-{"RELEASE-MANIFEST.json"}: raise SystemExit("candidate asset list differs from five-platform contract")
entries={}
for line in sums.read_text(encoding="ascii").splitlines():
 m=re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)",line)
 if not m or m.group(2) in entries: raise SystemExit("malformed or duplicate SHA256SUMS entry")
 entries[m.group(2)]=m.group(1)
if set(entries)!=required: raise SystemExit("SHA256SUMS names do not match the manifest")
for name,digest in entries.items():
 path=root/name
 if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise SystemExit(f"candidate checksum mismatch: {name}")
print(version)
