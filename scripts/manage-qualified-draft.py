#!/usr/bin/env python3
"""Only release writer: authenticated frozen candidate, explicit gates and revocation."""
import json,os,sys
from pathlib import Path
from release_policy import API,ALL,BUNDLE,CORE,MANIFEST,SEAL,SUMS,CONFIG,PUBLIC,allow_cleanup,allow_promotion,asset_identity,canonical,digest,positive,revoked_tags,same_assets,summary,verify_attestation

def latest(api):
 try:return api.request('releases/latest')
 except ValueError:
  if any(not r.get('draft') and not r.get('prerelease') for r in api.releases()):raise
  return None

def policy(api,tag):
 data,_=api.file('REVOKED',missing=True);current=latest(api)
 allow_promotion(tag,current['tag_name'] if current else None,revoked_tags(data.decode()))
 return current

def record(api,manifest,request,outcome):
 data,_=api.file('release-state.json',missing=True);state=json.loads(data) if data else {'format':'native-release-state/2','candidates':{}}
 previous=state['candidates'].get(manifest['tag'])
 if previous and previous['request']!=request:raise ValueError('conflicting recorded release identity')
 state['candidates'][manifest['tag']]={'request':request,'outcome':outcome,'private_run':'https://github.com/'+manifest['private_repository']+'/actions/runs/'+manifest['run_id'],'public_run':'https://github.com/'+PUBLIC+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID','offline'),'qualification_run':'https://github.com/'+PUBLIC+'/actions/runs/'+os.environ.get('QUALIFICATION_RUN_ID','offline')}
 api.put_file('release-state.json',canonical(state),'Record qualified release identity '+manifest['tag'])

def revoke(api,tag,reason):
 data,_=api.file('REVOKED',missing=True)
 if tag not in revoked_tags(data.decode()):api.put_file('REVOKED',data+(b'' if not data or data.endswith(b'\n') else b'\n')+(tag+' '+reason+'\n').encode(),'Revoke release candidate '+tag)

def identities(root,seal,request):
 return seal['assets']+[
  {'id':positive(request['seal_asset_id']),'name':SEAL,'digest':'sha256:'+digest((root/SEAL).read_bytes()),'size':(root/SEAL).stat().st_size},
  {'id':positive(request['bundle_asset_id']),'name':BUNDLE,'digest':'sha256:'+digest((root/BUNDLE).read_bytes()),'size':(root/BUNDLE).stat().st_size}]

def recheck(api,root,seal,request,download):
 release,etag=api.request('releases/'+str(positive(seal['release_id'])),with_headers=True)
 if release.get('tag_name')!=request['tag'] or release.get('target_commitish')!=CONFIG['branch']:raise ValueError('release target/tag changed')
 same_assets(identities(root,seal,request),release.get('assets',[]))
 if download:
  for asset in release['assets']:
   if digest(api.asset(asset['id']))!=asset['digest'].removeprefix('sha256:'):raise ValueError('live release bytes changed: '+asset['name'])
 return release,etag

def conditional(etag):
 # GitHub exposes weak ETags on some endpoints. Never pretend those provide CAS.
 return {'If-Match':etag} if etag and not etag.startswith('W/') else {}

def main():
 if len(sys.argv)!=3 or sys.argv[1] not in {'promote','cleanup'}:raise ValueError('usage: manage-qualified-draft.py promote|cleanup DIRECTORY')
 mode=sys.argv[1];root=Path(sys.argv[2]);m,seal=verify_attestation(root);request=json.loads((root/'candidate-request.json').read_text())
 expected={'tag':os.environ['DRAFT_TAG'],'seal_asset_id':positive(os.environ['SEAL_ASSET_ID']),'bundle_asset_id':positive(os.environ['BUNDLE_ASSET_ID']),'seal_sha256':os.environ['FREEZE_SHA']}
 if request!=expected or digest((root/SEAL).read_bytes())!=expected['seal_sha256'] or m['tag']!=expected['tag']:raise ValueError('qualified handoff identity changed')
 api=API();tag=m['tag']
 if mode=='cleanup':allow_cleanup(m)
 else:
  if m['deliberate_failure']:raise ValueError('throwaway candidate can never be promoted')
  policy(api,tag)
 release,etag=recheck(api,root,seal,request,True)
 if mode=='cleanup':
  if release.get('draft') is not True:raise ValueError('cleanup refuses a published release')
  revoke(api,tag,'sealed throwaway qualification failure')
  record(api,m,request,'revoked-throwaway')
  release,etag=recheck(api,root,seal,request,False)
  if release.get('draft') is not True:raise ValueError('draft state changed before cleanup')
  api.request('releases/'+str(release['id']),method='DELETE',headers=conditional(etag))
  summary('Revoked sealed throwaway and deleted only draft object '+tag+'; tag refs untouched.');print('Cleaned verified throwaway '+tag);return
 if release.get('draft') is False:
  policy(api,tag);record(api,m,request,'published');print('Identical current published candidate: no publication PATCH');return
 if release.get('draft') is not True:raise ValueError('invalid release draft state')
 # Re-read the full asset identity after downloads, directly before publication.
 policy(api,tag);release,etag=recheck(api,root,seal,request,False)
 if release.get('draft') is not True:raise ValueError('draft state changed before publication')
 # Do not move Latest until GitHub has locked the complete tested asset set.
 result=api.request('releases/'+str(release['id']),method='PATCH',headers=conditional(etag),data={'draft':False,'make_latest':'false'})
 if result.get('draft') is not False or result.get('tag_name')!=tag:raise ValueError('GitHub did not confirm publication')
 try:
  published,etag=recheck(api,root,seal,request,False)
  if published.get('immutable') is not True:raise ValueError('release immutability is required before Latest')
  policy(api,tag)
 except ValueError:
  revoke(api,tag,'publication identity/immutability check failed')
  # Removing a suspect release object never removes its tag and cannot promote it.
  api.request('releases/'+str(release['id']),method='DELETE')
  raise
 api.request('releases/'+str(release['id']),method='PATCH',headers=conditional(etag),data={'make_latest':'true'})
 final,_=recheck(api,root,seal,request,False)
 if final.get('draft') is not False or not final.get('immutable') or latest(api).get('id')!=release['id']:raise ValueError('GitHub did not confirm immutable Latest identity')
 record(api,m,request,'published');summary('Published immutable qualified '+tag+' as Latest.');print('Promoted immutable qualified '+tag)

if __name__=='__main__':
 try:main()
 except (ValueError,KeyError,OSError) as error:
  summary('Release mutation refused: '+str(error));raise SystemExit(str(error))
