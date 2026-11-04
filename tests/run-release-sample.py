#!/usr/bin/env python3
"""Exercise a user-facing lmctl autorun using the installed draft host."""
import argparse
import json
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
p.add_argument("--compiler",required=True)
p.add_argument("--host",required=True)
p.add_argument("--workdir",required=True,type=Path)
a=p.parse_args()
root=Path(__file__).resolve().parents[1];work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=True)
compiler=Path(a.compiler);cli=compiler.with_name("lmctl.cmd" if os.name=="nt" else "lmctl")
command=[str(cli),"autorun",str(root/"examples/5slidedeck.lms")]
if os.name=="nt" and cli.suffix.lower() in (".cmd",".bat"):
 # cmd /s /c strips the quote pair around the complete command and caused
 # Node to execute the batch shim itself as JavaScript on current runners.
 command=["cmd.exe","/d","/c","call "+subprocess.list2cmdline(command)]
env=dict(os.environ,PATH=str(Path(a.host).resolve().parent)+os.pathsep+str(compiler.parent)+os.pathsep+os.environ.get("PATH",""))
run=subprocess.run(command,cwd=work,env=env,text=True,capture_output=True)
if run.returncode: raise SystemExit("lmctl autorun failed:\n"+run.stdout+run.stderr)
output=work/"5slidedeck.pptx"
if not output.is_file(): raise SystemExit("lmctl autorun did not create the PPTX")
inspect=subprocess.run([a.host,"inspect",str(output)],cwd=work,env=env,text=True,capture_output=True)
if inspect.returncode: raise SystemExit("draft host inspect failed:\n"+inspect.stdout+inspect.stderr)
result=json.loads(inspect.stdout)
if result.get("ok") is not True or result.get("result",{}).get("valid") is not True or result["result"].get("slides")!=5:
 raise SystemExit("draft sample did not round-trip as a valid five-slide PPTX: "+json.dumps(result))
print("PASS lmctl autorun and draft host inspect: five-slide PPTX valid")
