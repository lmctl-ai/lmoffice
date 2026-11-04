#!/usr/bin/env python3
"""Download a public draft release by API release/asset IDs using gh's token."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

if len(sys.argv)!=4: raise SystemExit("usage: download-draft-candidate.py TAG SHA256SUMS_SHA256 OUTPUT_DIR")
tag,expected_sums_sha,out=sys.argv[1:];root=Path(out);root.mkdir(parents=True,exist_ok=True)
if not re.fullmatch(r"v\d+\.\d+\.\d+",tag): raise SystemExit("invalid draft tag")
if not re.fullmatch(r"[0-9a-f]{64}",expected_sums_sha): raise SystemExit("invalid dispatch SHA256SUMS digest")
try: releases=json.load(sys.stdin)
except Exception as error: raise SystemExit(f"cannot parse public release listing: {error}")
if not isinstance(releases,list): raise SystemExit("public release listing is not a JSON array")
if releases and isinstance(releases[0],list): releases=[release for page in releases for release in page]
matches=[r for r in releases if isinstance(r,dict) and r.get("tag_name")==tag]
if len(matches)!=1: raise SystemExit(f"expected exactly one visible release for {tag}, found {len(matches)}")
release=matches[0]
expected={"lmoffice-linux-x64","lmoffice-linux-arm64","lmoffice-macos-arm64","lmoffice-macos-x64","lmoffice-windows-x64.exe","LICENSE","THIRD_PARTY_NOTICES.md","RELEASE-MANIFEST.json","SHA256SUMS"}
assets=release.get("assets",[])
if {a.get("name") for a in assets if isinstance(a,dict)}!=expected: raise SystemExit("public draft asset list is incomplete or contains extra assets")
for asset in assets:
 name=asset["name"]
 if not re.fullmatch(r"[A-Za-z0-9_.-]+",name): raise SystemExit("unsafe release asset name")
 url=asset.get("url")
 if not isinstance(url,str) or not url.startswith("https://api.github.com/repos/lmctl-ai/lmoffice/releases/assets/"):
  raise SystemExit(f"unexpected asset API URL for {name}")
 result=subprocess.run(["gh","api",url,"-H","Accept: application/octet-stream"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if result.returncode: raise SystemExit(f"draft asset download failed for {name} (gh api exit {result.returncode})")
 if len(result.stdout)!=asset.get("size"): raise SystemExit(f"draft asset size mismatch for {name}")
 (root/name).write_bytes(result.stdout)
sums_sha=hashlib.sha256((root/"SHA256SUMS").read_bytes()).hexdigest()
if sums_sha!=expected_sums_sha: raise SystemExit("downloaded draft SHA256SUMS differs from repository_dispatch payload")
if not release.get("draft"):
 print(f"Release {tag} is already published with the same candidate identity; qualification replay is idempotent")
else:
 print(f"Downloaded {len(assets)} draft release assets for {tag} through authenticated asset IDs")
