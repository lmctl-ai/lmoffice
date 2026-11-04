#!/usr/bin/env python3
"""Install and verify the exact draft binary through the normal lmscript resolver."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

parser=argparse.ArgumentParser()
parser.add_argument("--compiler",required=True)
parser.add_argument("--tag",required=True)
parser.add_argument("--asset",required=True)
parser.add_argument("--candidate",required=True,type=Path)
a=parser.parse_args()
if not re.fullmatch(r"v\d+\.\d+\.\d+",a.tag): raise SystemExit("invalid draft tag")
allowed={"lmoffice-linux-x64","lmoffice-linux-arm64","lmoffice-macos-arm64","lmoffice-macos-x64","lmoffice-windows-x64.exe"}
if a.asset not in allowed: raise SystemExit("invalid platform asset name")
compiler=Path(a.compiler);command=[str(compiler),"install",f"github:lmctl-ai/lmoffice@{a.tag}"]
if os.name=="nt" and compiler.suffix.lower() in (".cmd",".bat"):
 command=["cmd.exe","/d","/s","/c",subprocess.list2cmdline(command)]
result=subprocess.run(command,text=True,capture_output=True)
if result.returncode:
 sys.stderr.write(result.stderr)
 raise SystemExit(result.returncode)
install_info={}
for line in result.stdout.splitlines():
 if ":" in line:
  key,value=line.split(":",1);install_info[key.strip()]=value.strip()
exe=".exe" if os.name=="nt" else ""
cache=Path(os.environ["LMSCRIPT_TOOL_CACHE"])
binary=cache/"github"/"lmctl-ai"/"lmoffice"/a.tag/("lmoffice"+exe)
if install_info.get("source")!="tool cache" or Path(install_info.get("path",""))!=binary:
 raise SystemExit("lmscript did not install the exact draft into this job's isolated tool cache")
if not binary.is_file(): raise SystemExit(f"lmscript install did not create the expected executable: {binary}")
checksums={}
for line in (a.candidate/"SHA256SUMS").read_text(encoding="ascii").splitlines():
 digest,name=line.split("  ",1);checksums[name]=digest
if hashlib.sha256(binary.read_bytes()).hexdigest()!=checksums.get(a.asset): raise SystemExit("installed host bytes differ from the sealed draft asset")
manifest=json.loads((a.candidate/"RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
version=subprocess.run([str(binary),"--version"],check=True,text=True,capture_output=True).stdout.strip()
if version!="lmoffice "+manifest["version"]: raise SystemExit(f"candidate --version mismatch: {version!r}")
with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as f: f.write(f"LMOFFICE_BIN={binary}\n")
with open(os.environ["GITHUB_PATH"],"a",encoding="utf-8") as f: f.write(str(binary.parent)+"\n")
print(f"Installed exact {a.tag} via lmscript; candidate asset SHA-256 verified")
