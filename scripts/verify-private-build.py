#!/usr/bin/env python3
"""Verify source/build attempt through the private run API using actions:read only."""
import json,os,sys
from pathlib import Path
from release_policy import API,CONFIG,PRIVATE,canonical,positive,summary,validate_producer
root=Path(sys.argv[1]);m=json.loads((root/'RELEASE-MANIFEST.json').read_text())
for key,value in {'private_repository':PRIVATE,'workflow':CONFIG['workflow'],'branch':CONFIG['branch'],'ref':'refs/heads/'+CONFIG['branch'],'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID']}.items():
 if m.get(key)!=value:raise SystemExit('private build manifest mismatch: '+key)
if m.get('tag')!=os.environ['EXPECTED_TAG']:raise SystemExit('build artifact tag differs from trusted version job output')
purpose=os.environ['DELIBERATE_FAILURE']
if purpose not in {'true','false'} or type(m.get('deliberate_failure')) is not bool or m['deliberate_failure']!=(purpose=='true'):raise SystemExit('build artifact throwaway flag differs from trusted workflow input')
run_id=str(positive(m['run_id']));attempt=str(positive(m['run_attempt']));api=API(PRIVATE)
run=api.request('actions/runs/'+run_id+'/attempts/'+attempt)
expected={'id':run_id,'attempt':attempt,'head_sha':m['source_sha'],'head_branch':CONFIG['branch'],'path':CONFIG['workflow'],'event':'workflow_dispatch'}
actual={'id':str(run['id']),'attempt':str(run['run_attempt']),'head_sha':run['head_sha'],'head_branch':run['head_branch'],'path':run['path'].split('@',1)[0],'event':run['event']}
if actual!=expected:raise SystemExit('private run API identity does not match candidate source')
jobs=[];page=1
while True:
 batch=api.request('actions/runs/'+run_id+'/attempts/'+attempt+'/jobs?per_page=100&page='+str(page))['jobs'];jobs+=batch
 if len(batch)<100:break
 page+=1
receipt=[]
for name in CONFIG['private_jobs']:
 matches=[j for j in jobs if j['name']==name]
 if len(matches)!=1 or matches[0]['conclusion']!='success' or matches[0]['status']!='completed':raise SystemExit('private API prerequisite is not successful: '+name)
 job=matches[0];receipt.append({k:job[k] for k in ['id','name','status','conclusion']})
actual['jobs']=receipt;m['private_run']=actual;validate_producer(m);(root/'PRIVATE-RUN.json').write_bytes(canonical(actual));summary('Verified source SHA, workflow, main ref and all eight prerequisite jobs through the private actions:read API.')
