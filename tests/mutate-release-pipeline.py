#!/usr/bin/env python3
"""Mutate an isolated source snapshot; the normal offline suite must go red."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
mutations=[
 ('credential-inheritance','scripts/release_policy.py',"return {k:v for k,v in env.items() if k not in {'GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN','ACTIONS_ID_TOKEN_REQUEST_URL'}}",'return dict(env)'),
 ('producer-identity','scripts/release_policy.py',"m.get('private_repository')!=PRIVATE","False"),
 ('certificate-run','scripts/release_policy.py',"if parts[4]==str(m['run_id']) and positive(parts[6])>=positive(m['run_attempt']):","if True:"),
 ('sealed-cleanup','scripts/release_policy.py',"if manifest.get('deliberate_failure') is not True:","if False:"),
 ('older-candidate','scripts/release_policy.py',"if latest and key<version(latest):","if False:"),
 ('revoked-candidate','scripts/release_policy.py',"if tag in revoked:","if False:"),
 ('asset-id','scripts/release_policy.py',"'id':positive(asset['id'])","'id':1"),
 ('late-recheck','scripts/manage-qualified-draft.py',"policy(api,tag);release,etag=recheck(api,root,seal,request,False)","policy(api,tag)"),
 ('frozen-repair','scripts/stage-frozen-draft.py',"if any(a['name'] in {SEAL,BUNDLE} for a in release.get('assets',[])) and name!=BUNDLE:","if False:"),
 ('cancel',' .github/workflows/qualify-private-draft.yml'.strip(),"!cancelled() && ",""),
 ('queue-candidate','.github/workflows/qualify-private-draft.yml',"group: lmoffice-qualification-${{ inputs.tag || github.event.client_payload.tag }}","group: one-shared-pending-slot"),
 ('queue-writer','.github/workflows/qualify-private-draft.yml',"      queue: max\n",""),
 ('action-pin','.github/workflows/qualify-private-draft.yml','actions/checkout@11d5960a326750d5838078e36cf38b85af677262','actions/checkout@v4'),
 ('doc-permissions','docs/release-pipeline.md','| promote | contents:write |','| promote | contents:read |'),
]
with tempfile.TemporaryDirectory(prefix='release-mutations-') as temporary:
 root=Path(temporary)
 for name in ['scripts','tests','.github','docs']:
  shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copy2(ROOT/'release-policy.json',root/'release-policy.json')
 command=[sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_release*.py']
 baseline=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if baseline.returncode:sys.stdout.buffer.write(baseline.stdout);raise SystemExit('mutation baseline is not green')
 for name,file,old,new in mutations:
  p=root/file;source=p.read_text()
  if old not in source:raise SystemExit('mutation target not found: '+name)
  try:
   p.write_text(source.replace(old,new,1));r=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
   if r.returncode==0:raise SystemExit('SURVIVED '+name)
   if b'ModuleNotFoundError' in r.stdout or b'SyntaxError' in r.stdout:sys.stdout.buffer.write(r.stdout);raise SystemExit('invalid control '+name)
   print('CAUGHT '+name,flush=True)
  finally:p.write_text(source)
print('PASS '+str(len(mutations))+' release mutations')
