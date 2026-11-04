#!/usr/bin/env python3
"""Stage the exact draft asset on PATH and verify lmscript resolves that binary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from release_policy import credential_free

parser=argparse.ArgumentParser()
parser.add_argument("--compiler",required=True)
parser.add_argument("--tag",required=True)
parser.add_argument("--asset",required=True)
parser.add_argument("--candidate",required=True,type=Path)
a=parser.parse_args()
if not re.fullmatch(r"v\d+\.\d+\.\d+",a.tag): raise SystemExit("invalid draft tag")
allowed={"lmoffice-linux-x64","lmoffice-linux-arm64","lmoffice-macos-arm64","lmoffice-macos-x64","lmoffice-windows-x64.exe"}
if a.asset not in allowed: raise SystemExit("invalid platform asset name")
checksums={}
for line in (a.candidate/"SHA256SUMS").read_text(encoding="ascii").splitlines():
 digest,name=line.split("  ",1);checksums[name]=digest
manifest=json.loads((a.candidate/"RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
if manifest.get("tag")!=a.tag or checksums.get(a.asset) is None: raise SystemExit("candidate tag/asset metadata mismatch")
exe=".exe" if os.name=="nt" else ""
binary_name="lmoffice"+exe
host_dir=Path(os.environ["RUNNER_TEMP"])/"lmoffice-draft-bin";host_dir.mkdir(parents=True,exist_ok=True)
binary=host_dir/binary_name
shutil.copyfile(a.candidate/a.asset,binary)
if os.name!="nt":binary.chmod(0o755)
compiler=Path(a.compiler);command=[str(compiler),"install",f"github:lmctl-ai/lmoffice@{a.tag}"]
if os.name=="nt" and compiler.suffix.lower() in (".cmd",".bat"):
 command=["cmd.exe","/d","/s","/c",subprocess.list2cmdline(command)]
env=dict(credential_free(os.environ),PATH=str(host_dir)+os.pathsep+str(compiler.parent)+os.pathsep+os.environ.get("PATH",""))
result=subprocess.run(command,text=True,capture_output=True,env=env)
if result.returncode:
 sys.stderr.write(result.stderr)
 raise SystemExit(result.returncode)
install_info={}
for line in result.stdout.splitlines():
 if ":" in line:
  key,value=line.split(":",1);install_info[key.strip()]=value.strip()
if install_info.get("source")!="PATH" or Path(install_info.get("path",""))!=binary:
 raise SystemExit("lmscript did not resolve the exact candidate from its isolated PATH")
if hashlib.sha256(binary.read_bytes()).hexdigest()!=checksums[a.asset]: raise SystemExit("candidate host bytes differ from the sealed draft asset")
version=subprocess.run([str(binary),"--version"],check=True,text=True,capture_output=True,env=credential_free(os.environ)).stdout.strip()
if version!="lmoffice "+manifest["version"]: raise SystemExit(f"candidate --version mismatch: {version!r}")
with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as f: f.write(f"LMOFFICE_BIN={binary}\n")
with open(os.environ["GITHUB_PATH"],"a",encoding="utf-8") as f: f.write(str(host_dir)+"\n")
print(f"Staged exact {a.tag} asset on the user PATH; lmscript install resolved it and its SHA-256 verified")
