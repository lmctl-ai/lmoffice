#!/usr/bin/env python3
"""Trusted read-only handoff using fixed asset IDs, never candidate execution."""
import json,os,sys
from pathlib import Path
from release_policy import API,ALL,BUNDLE,CORE,SEAL,CONFIG,PUBLIC,positive,hexadecimal,digest,allow_promotion,revoked_tags,verify_attestation,output,summary

def main():
 api=API();tag=os.environ['DRAFT_TAG'];root=Path('draft-assets');root.mkdir(exist_ok=True)
 revocations,_=api.file('REVOKED',missing=True)
 try:latest=api.request('releases/latest')['tag_name']
 except ValueError:
  if any(not r.get('draft') and not r.get('prerelease') for r in api.releases()):raise
  latest=None
 allow_promotion(tag,latest,revoked_tags(revocations.decode()))
 if os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch':
  state,_=api.file('release-state.json');record=json.loads(state)['candidates'].get(tag)
  if not record:raise ValueError('manual replay requires a previously recorded candidate')
  request=record['request']
 else:
  request={'tag':tag,'seal_asset_id':positive(os.environ['SEAL_ASSET_ID']),'bundle_asset_id':positive(os.environ['BUNDLE_ASSET_ID']),'seal_sha256':os.environ['FREEZE_SHA']}
 if request['tag']!=tag or not hexadecimal(request['seal_sha256'],64):raise ValueError('invalid replay/dispatch identity')
 data=api.asset(request['seal_asset_id'])
 if digest(data)!=request['seal_sha256']:raise ValueError('frozen identity differs from dispatch')
 (root/SEAL).write_bytes(data);seal=json.loads(data)
 if seal.get('repository')!=PUBLIC or seal.get('tag')!=tag or {a.get('name') for a in seal.get('assets',[])}!=CORE:raise ValueError('invalid frozen release contract')
 for a in seal['assets']:
  data=api.asset(a['id'])
  if digest(data)!=a['digest'].removeprefix('sha256:') or len(data)!=a['size']:raise ValueError('downloaded frozen asset mismatch: '+a['name'])
  (root/a['name']).write_bytes(data)
 (root/BUNDLE).write_bytes(api.asset(request['bundle_asset_id']))
 m,seal=verify_attestation(root)
 if m['tag']!=tag:raise ValueError('attested candidate has another tag')
 (root/'candidate-request.json').write_text(json.dumps(request)+'\n')
 output({'tag':tag,'version':m['version'],'failure_control':str(m['deliberate_failure']).lower(),'seal_asset_id':request['seal_asset_id'],'bundle_asset_id':request['bundle_asset_id'],'seal_sha256':request['seal_sha256'],'sums_sha256':digest((root/'SHA256SUMS').read_bytes())})
 summary('Verified private provenance and frozen asset identities for '+tag+'; original private run '+m['run_id']+' attempt '+m['run_attempt'])
 print('Verified trusted draft handoff for '+tag)

if __name__=='__main__':
 try:main()
 except (ValueError,KeyError,OSError) as error:
  summary('Candidate refused: '+str(error));raise SystemExit(str(error))
