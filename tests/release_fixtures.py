"""Synthetic protocol fixture and in-memory API; tests never contact GitHub."""
from pathlib import Path
import copy,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import release_policy as policy

def candidate(root,tag='v1.2.3',throwaway=False):
 root=Path(root);root.mkdir(parents=True,exist_ok=True);assets=[]
 for n in sorted(policy.PAYLOADS):
  data=('synthetic '+n+'\n').encode();(root/n).write_bytes(data);assets.append({'id':len(assets)+1,'name':n,'digest':'sha256:'+policy.digest(data),'size':len(data)})
 receipt={'id':'123','attempt':'1','head_sha':'a'*40,'head_branch':'main','path':'.github/workflows/ci.yml','event':'workflow_dispatch','jobs':[{'id':i+100,'name':n,'status':'completed','conclusion':'success'} for i,n in enumerate(policy.CONFIG['private_jobs'])]}
 m={'format':'native-release-candidate/2','repository':policy.PUBLIC,'private_repository':policy.PRIVATE,'workflow':policy.CONFIG['workflow'],'branch':'main','ref':'refs/heads/main','source_sha':'a'*40,'run_id':'123','run_attempt':'1','tag':tag,'version':tag[1:],'deliberate_failure':throwaway,'private_run':receipt,'assets':assets}
 (root/policy.MANIFEST).write_bytes(policy.canonical(m));(root/policy.SUMS).write_text(''.join(policy.digest((root/n).read_bytes())+'  '+n+'\n' for n in sorted(policy.PAYLOADS|{policy.MANIFEST})))
 for name in [policy.MANIFEST,policy.SUMS]:
  data=(root/name).read_bytes();assets=assets+[{'id':len(assets)+1,'name':name,'digest':'sha256:'+policy.digest(data),'size':len(data)}]
 seal={'format':'native-release-freeze/2','repository':policy.PUBLIC,'tag':tag,'release_id':77,'assets':assets};(root/policy.SEAL).write_bytes(policy.canonical(seal));(root/policy.BUNDLE).write_text('synthetic attestation; never cryptographically accepted\n')
 request={'tag':tag,'seal_asset_id':10,'bundle_asset_id':11,'seal_sha256':policy.digest((root/policy.SEAL).read_bytes())};(root/'candidate-request.json').write_bytes(policy.canonical(request))
 return m,seal,request

class MemoryAPI:
 def __init__(self,root,seal,request,latest='v1.2.2',revoked='',draft=True,race=False):
  self.root=Path(root);self.files={'REVOKED':revoked.encode(),'release-state.json':b'{"format":"native-release-state/2","candidates":{}}'};self.blobs={};self.patches=[];self.deleted=[];self.race=race;self.release_gets=0
  assets=copy.deepcopy(seal['assets'])
  for name,key in [(policy.SEAL,'seal_asset_id'),(policy.BUNDLE,'bundle_asset_id')]:
   data=(self.root/name).read_bytes();assets.append({'name':name,'id':request[key],'digest':'sha256:'+policy.digest(data),'size':len(data)})
  for a in assets:self.blobs[a['id']]=(self.root/a['name']).read_bytes()
  self.release={'id':seal['release_id'],'tag_name':request['tag'],'target_commitish':'main','draft':draft,'immutable':not draft,'assets':assets}
  self.latest={'id':66,'tag_name':latest,'draft':False,'prerelease':False} if latest else None
 def file(self,name,missing=False):return self.files.get(name,b''),None
 def put_file(self,name,data,message):self.files[name]=data
 def asset(self,identifier):return self.blobs[int(identifier)]
 def releases(self):return [self.release]+([self.latest] if self.latest else [])
 def request(self,path,method='GET',data=None,headers=None,raw=False,with_headers=False):
  if path=='releases/latest':
   if self.latest is None:raise ValueError('no latest')
   return copy.deepcopy(self.latest)
  if path=='releases/77':
   if method=='GET':
    self.release_gets+=1
    if self.race and self.release_gets==2:self.release['assets'][0]['id']=900
    out=copy.deepcopy(self.release);return (out,'"revision-'+str(self.release_gets)+'"') if with_headers else out
   if method=='PATCH':
    self.patches.append(copy.deepcopy(data))
    if 'draft' in data:self.release['draft']=data['draft'];self.release['immutable']=not data['draft']
    if data.get('make_latest')=='true':self.latest=self.release
    return copy.deepcopy(self.release)
   if method=='DELETE':self.deleted.append(77);return None
  raise AssertionError((path,method,data))
