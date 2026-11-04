#!/usr/bin/env python3
"""Read-only child gate: verify the parent run/artifact, then local signed bytes."""
import json,os
from pathlib import Path
from release_policy import API,CONFIG,positive,output,summary,verify_attestation
api=API();event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['client_payload'];parent=positive(event['parent_run_id']);attempt=positive(event['parent_attempt']);artifact=positive(event['artifact_id'])
run=api.request('actions/runs/'+str(parent)+'/attempts/'+str(attempt))
if run['path'].split('@',1)[0]!='.github/workflows/qualify-private-draft.yml' or run['head_sha']!=os.environ['GITHUB_SHA'] or run['head_branch']!=CONFIG['branch'] or run['status']!='in_progress' or run['event'] not in {'repository_dispatch','workflow_dispatch'}:raise SystemExit('parent is not the active trusted release broker at this public source SHA')
a=api.request('actions/artifacts/'+str(artifact))
if a.get('expired') or a.get('workflow_run',{}).get('id')!=parent or a.get('name')!=f'lmoffice-draft-{parent}-{attempt}' or a.get('digest')!='sha256:'+event['artifact_digest']:raise SystemExit('public artifact does not belong to the active broker identity')
m,seal=verify_attestation(Path('draft-assets'))
if m['tag']!=event['tag']:raise SystemExit('qualification tag differs from attested candidate')
output({'tag':m['tag'],'failure_control':str(m['deliberate_failure']).lower(),'sums_sha256':next(x['digest'][7:] for x in seal['assets'] if x['name']=='SHA256SUMS')})
summary('Verified active broker run, immutable artifact digest and private provenance before native execution.')
