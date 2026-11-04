#!/usr/bin/env python3
"""Upload missing candidate assets once. Never clobber/delete an existing asset."""
import argparse,json,os,subprocess
from pathlib import Path
from release_policy import API,CONFIG,PUBLIC,PRIVATE,PAYLOADS,MANIFEST,SUMS,SEAL,BUNDLE,CORE,ALL,asset_identity,canonical,digest,output,same_assets,summary,validate_manifest,verify_attestation

def upload(api,release,name,path):
 existing=[a for a in release.get('assets',[]) if a['name']==name]
 data=path.read_bytes()
 if existing:
  if len(existing)!=1:raise ValueError('duplicate release asset')
  a=existing[0]
  if a.get('digest')!='sha256:'+digest(data) or a.get('size')!=len(data) or api.asset(a['id'])!=data:raise ValueError('existing candidate differs; frozen assets are never replaced: '+name)
  return a
 if any(a['name'] in {SEAL,BUNDLE} for a in release.get('assets',[])) and name!=BUNDLE:raise ValueError('frozen candidate cannot upload a missing asset: '+name)
 # A fresh upload has conflict semantics at the server. --clobber is forbidden.
 result=subprocess.run(['gh','release','upload',release['tag_name'],'--repo',PUBLIC,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if result.returncode:raise ValueError('upload failed without replacing existing assets: '+name)
 fresh=api.request('releases/'+str(release['id']));matches=[a for a in fresh['assets'] if a['name']==name]
 if len(matches)!=1:raise ValueError('uploaded asset not found exactly once')
 a=matches[0]
 if a.get('digest')!='sha256:'+digest(data) or a.get('size')!=len(data):raise ValueError('uploaded asset digest differs')
 release['assets']=fresh['assets'];return a

def main():
 if os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or os.environ.get('GITHUB_REF')!='refs/heads/'+CONFIG['branch']:raise ValueError('producer requires private workflow_dispatch on main')
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['stage','dispatch']);p.add_argument('directory',type=Path);p.add_argument('--bundle',type=Path);a=p.parse_args();root=a.directory;api=API()
 if a.mode=='dispatch':
  request=json.loads((root/'candidate-request.json').read_text());release=api.request('releases/'+str(request.pop('release_id')))
  seal=json.loads((root/SEAL).read_text());same_assets(seal['assets'],[x for x in release['assets'] if x['name'] in CORE])
  bundle=a.bundle if a.bundle else root/BUNDLE
  if bundle!=root/BUNDLE:(root/BUNDLE).write_bytes(bundle.read_bytes())
  provenance=upload(api,release,BUNDLE,root/BUNDLE);request['bundle_asset_id']=provenance['id']
  if {x['name'] for x in release['assets']}!=ALL:raise ValueError('frozen draft asset list is not complete')
  (root/'candidate-request.json').write_bytes(canonical(request))
  # Once dispatched, all retries are verification-only; the producer never removes assets.
  api.request('dispatches',method='POST',data={'event_type':CONFIG['product']+'-release-draft','client_payload':request})
  summary('Dispatched frozen '+request['tag']+'; seal SHA256 '+request['seal_sha256']);print('Dispatched verified frozen '+request['tag']);return
 core=json.loads((root/MANIFEST).read_text());receipt=json.loads((root/'PRIVATE-RUN.json').read_text())
 if core['source_sha']!=os.environ['GITHUB_SHA'] or core['run_id']!=os.environ['GITHUB_RUN_ID']:raise ValueError('foreign core candidate')
 # Verify the immutable build artifact before changing its core manifest into the final public one.
 core_entries={}
 for line in (root/SUMS).read_text('ascii').splitlines():
  h,sep,name=line.partition('  ')
  if not sep or name in core_entries or name not in PAYLOADS|{MANIFEST} or digest((root/name).read_bytes())!=h:raise ValueError('core candidate checksum mismatch')
  core_entries[name]=h
 if set(core_entries)!=PAYLOADS|{MANIFEST}:raise ValueError('core checksums incomplete')
 matches=[r for r in api.releases() if r['tag_name']==core['tag']]
 if len(matches)>1:raise ValueError('duplicate release tag')
 marker='Frozen producer '+core['run_id']+' attempt '+core['run_attempt']+' source '+core['source_sha']
 if matches:
  release=matches[0]
  if marker not in release.get('body',''):raise ValueError('existing tag belongs to a different producer identity')
 else:
  release=api.request('releases',method='POST',data={'tag_name':core['tag'],'target_commitish':CONFIG['branch'],'name':core['tag'],'body':marker+'\nPrivate verified candidate; public qualification pending.','draft':True,'prerelease':False,'make_latest':'false'})
 if {x['name'] for x in release.get('assets',[])}-ALL:raise ValueError('unexpected existing release assets')
 # Published retries may redispatch identical bytes, but never upload anything missing.
 if not release.get('draft') and {x['name'] for x in release['assets']}!=ALL:raise ValueError('published release has a conflicting asset set')
 payload=[]
 for name in sorted(PAYLOADS):payload.append(asset_identity(upload(api,release,name,root/name)))
 manifest={k:core[k] for k in ['repository','private_repository','workflow','branch','ref','source_sha','run_id','run_attempt','tag','version','deliberate_failure']}
 manifest.update(format='native-release-candidate/2',assets=payload,private_run=receipt);validate_manifest(manifest);(root/MANIFEST).write_bytes(canonical(manifest))
 upload(api,release,MANIFEST,root/MANIFEST)
 (root/SUMS).write_text(''.join(digest((root/name).read_bytes())+'  '+name+'\n' for name in sorted(PAYLOADS|{MANIFEST})))
 upload(api,release,SUMS,root/SUMS)
 fresh=api.request('releases/'+str(release['id']));identities=[asset_identity(x) for x in fresh['assets'] if x['name'] in CORE]
 seal={'format':'native-release-freeze/2','repository':PUBLIC,'tag':manifest['tag'],'release_id':release['id'],'assets':sorted(identities,key=lambda x:x['name'])}
 (root/SEAL).write_bytes(canonical(seal));frozen=upload(api,release,SEAL,root/SEAL)
 request={'tag':manifest['tag'],'release_id':release['id'],'seal_asset_id':frozen['id'],'seal_sha256':digest((root/SEAL).read_bytes())}
 existing=[x for x in release['assets'] if x['name']==BUNDLE]
 if existing:
  (root/BUNDLE).write_bytes(api.asset(existing[0]['id']));verify_attestation(root)
 (root/'candidate-request.json').write_bytes(canonical(request));output({'needs_attestation':str(not bool(existing)).lower()})
 summary('Frozen '+manifest['tag']+' with stable release/asset IDs; retries only reuse matching bytes.');print('Prepared immutable upload identities for '+manifest['tag'])

if __name__=='__main__':
 try:main()
 except (ValueError,KeyError,OSError) as error:summary('Private candidate refused: '+str(error));raise SystemExit(str(error))
