"""Release protocol v2: pure validation, GitHub I/O and private provenance verification.
No candidate executable is invoked by this trusted module.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'release-policy.json').read_text())
PUBLIC=CONFIG['public_repository'];PRIVATE=CONFIG['private_repository']
PAYLOADS=set(CONFIG['payloads'])
MANIFEST='RELEASE-MANIFEST.json';SUMS='SHA256SUMS';SEAL='FROZEN-CANDIDATE.json';BUNDLE='PROVENANCE.jsonl'
CORE=PAYLOADS|{MANIFEST,SUMS};ALL=CORE|{SEAL,BUNDLE}

def digest(data):return hashlib.sha256(data).hexdigest()
def canonical(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def hexadecimal(value,length):return isinstance(value,str) and len(value)==length and all(c in '0123456789abcdef' for c in value)
def positive(value):
 if isinstance(value,bool):raise ValueError('boolean is not a GitHub id')
 s=str(value)
 if not s or not all('0'<=c<='9' for c in s) or s[0]=='0':raise ValueError('invalid GitHub id')
 return int(s)
def version(tag):
 if not isinstance(tag,str) or not tag.startswith('v'):raise ValueError('expected stable vMAJOR.MINOR.PATCH tag')
 parts=tag[1:].split('.')
 if len(parts)!=3 or any(not p or not all('0'<=c<='9' for c in p) or len(p)>1 and p[0]=='0' for p in parts):raise ValueError('expected stable vMAJOR.MINOR.PATCH tag')
 return tuple((len(p),p) for p in parts)
def revoked_tags(text):
 out=[]
 for line in text.splitlines():
  line=line.strip()
  if not line or line.startswith('#'):continue
  tag=line.split()[0];version(tag);out.append(tag)
 return out

def allow_promotion(tag,latest,revoked):
 key=version(tag)
 if tag in revoked:raise ValueError('candidate is durably revoked: '+tag)
 if latest and key<version(latest):raise ValueError('refusing older candidate '+tag+' below Latest '+latest)

def allow_cleanup(manifest):
 if manifest.get('deliberate_failure') is not True:raise ValueError('cleanup requires sealed throwaway purpose')

def asset_identity(asset):
 return {'id':positive(asset['id']),'name':asset['name'],'digest':asset['digest'],'size':asset['size']}
def same_assets(expected,actual):
 left={a['name']:asset_identity(a) for a in expected};right={a['name']:asset_identity(a) for a in actual}
 if len(left)!=len(expected) or len(right)!=len(actual) or left!=right:raise ValueError('frozen release asset ids/digests/sizes changed')

def validate_producer(m):
 if m.get('format') not in {'native-release-core/2','native-release-candidate/2'} or m.get('repository')!=PUBLIC:raise ValueError('unsupported candidate manifest')
 tag=m.get('tag');version(tag)
 if m.get('version')!=tag[1:]:raise ValueError('manifest version/tag mismatch')
 if m.get('private_repository')!=PRIVATE or m.get('workflow')!=CONFIG['workflow'] or m.get('branch')!=CONFIG['branch'] or m.get('ref')!='refs/heads/'+CONFIG['branch']:raise ValueError('foreign private producer workflow/ref')
 if not hexadecimal(m.get('source_sha'),40) or m['source_sha']=='0'*40:raise ValueError('invalid private source commit')
 positive(m.get('run_id'));positive(m.get('run_attempt'))
 if type(m.get('deliberate_failure')) is not bool:raise ValueError('throwaway purpose must be sealed boolean')
 receipt=m.get('private_run',{})
 for key,want in {'id':str(m['run_id']),'attempt':str(m['run_attempt']),'head_sha':m['source_sha'],'head_branch':CONFIG['branch'],'path':CONFIG['workflow'],'event':'workflow_dispatch'}.items():
  if receipt.get(key)!=want:raise ValueError('private API verification receipt mismatch: '+key)
 jobs=receipt.get('jobs',[])
 if {j.get('name') for j in jobs}!=set(CONFIG['private_jobs']) or len(jobs)!=len(CONFIG['private_jobs']):raise ValueError('private API build gates incomplete')
 for job in jobs:
  positive(job['id'])
  if job.get('conclusion')!='success' or job.get('status')!='completed':raise ValueError('private build gate did not pass')
 return m

def validate_manifest(m):
 if m.get('format')!='native-release-candidate/2':raise ValueError('unsupported candidate manifest')
 validate_producer(m)
 assets=m.get('assets',[])
 if {a.get('name') for a in assets}!=PAYLOADS or len(assets)!=len(PAYLOADS):raise ValueError('manifest payload list mismatch')
 for a in assets:validate_asset(a)
 return m

def validate_asset(a):
 positive(a.get('id'))
 if not isinstance(a.get('size'),int) or isinstance(a['size'],bool) or a['size']<=0:raise ValueError('empty/invalid release asset size')
 h=a.get('digest','')
 if not isinstance(h,str) or not h.startswith('sha256:') or not hexadecimal(h[7:],64):raise ValueError('invalid asset digest')
 return a

def validate_files(root):
 root=Path(root);m=validate_manifest(json.loads((root/MANIFEST).read_text()))
 seal=json.loads((root/SEAL).read_text())
 if seal.get('format')!='native-release-freeze/2' or seal.get('tag')!=m['tag'] or seal.get('repository')!=PUBLIC:raise ValueError('foreign freeze identity')
 positive(seal.get('release_id'))
 assets=seal.get('assets',[])
 if {a.get('name') for a in assets}!=CORE or len(assets)!=len(CORE):raise ValueError('freeze must cover all payload/manifest/checksum assets')
 same_assets(m['assets'],[a for a in assets if a['name'] in PAYLOADS])
 for a in assets:
  validate_asset(a);data=(root/a['name']).read_bytes()
  if len(data)!=a['size'] or 'sha256:'+digest(data)!=a['digest']:raise ValueError('frozen bytes differ: '+a['name'])
 entries={}
 for line in (root/SUMS).read_text('ascii').splitlines():
  h,sep,name=line.partition('  ')
  if not sep or not hexadecimal(h,64) or name in entries:raise ValueError('malformed/duplicate checksum entry')
  entries[name]=h
 if set(entries)!=PAYLOADS|{MANIFEST}:raise ValueError('checksum file must cover all payloads and manifest')
 for name,h in entries.items():
  if digest((root/name).read_bytes())!=h:raise ValueError('checksum mismatch: '+name)
 return m,seal

def credential_free(env):
 return {k:v for k,v in env.items() if k not in {'GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN','ACTIONS_ID_TOKEN_REQUEST_URL'}}

class API:
 def __init__(self,repo=PUBLIC):self.repo=repo
 def request(self,path,method='GET',data=None,headers=None,raw=False,with_headers=False):
  args=['gh','api','--method',method]
  if with_headers:args.append('--include')
  for key,value in (headers or {}).items():args+=['-H',key+': '+value]
  args.append('repos/'+self.repo+'/'+path)
  if data is not None:args+=['--input','-']
  result=subprocess.run(args,input=None if data is None else json.dumps(data).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  if result.returncode:raise ValueError('GitHub API '+method+' '+path+' failed (gh exit '+str(result.returncode)+')')
  content=result.stdout;etag=None
  if with_headers:
   # gh --include prints HTTP headers before the response, sometimes with LF only.
   normalized=content.replace(b'\r\n',b'\n');head,sep,content=normalized.partition(b'\n\n')
   if not sep:raise ValueError('GitHub response missing headers')
   for line in head.decode('ascii').splitlines():
    k,_,v=line.partition(':')
    if k.lower()=='etag':etag=v.strip()
  value=content if raw else (json.loads(content) if content.strip() else None)
  return (value,etag) if with_headers else value
 def asset(self,identifier):return self.request('releases/assets/'+str(positive(identifier)),headers={'Accept':'application/octet-stream'},raw=True)
 def releases(self):
  out=[];page=1
  while True:
   batch=self.request('releases?per_page=100&page='+str(page));out+=batch
   if len(batch)<100:return out
   page+=1
 def file(self,path,missing=False):
  try:r=self.request('contents/'+path+'?ref='+CONFIG['branch'])
  except ValueError:
   if not missing:raise
   # A list query distinguishes absent optional policy files from auth/network failures.
   names={x['name'] for x in self.request('contents/?ref='+CONFIG['branch'])}
   if path not in names:return b'',None
   raise
  return base64.b64decode(r['content']),r['sha']
 def put_file(self,path,data,message):
  old,sha=self.file(path,missing=True)
  if old==data:return
  payload={'message':message,'content':base64.b64encode(data).decode(),'branch':CONFIG['branch']}
  if sha:payload['sha']=sha
  self.request('contents/'+path,method='PUT',data=payload)


def verify_attestation(root):
 root=Path(root);m,seal=validate_files(root)
 args=['gh','attestation','verify',str(root/SEAL),'--bundle',str(root/BUNDLE),'--repo',PRIVATE,'--signer-workflow',PRIVATE+'/'+CONFIG['workflow'],'--source-ref',m['ref'],'--source-digest',m['source_sha'],'--deny-self-hosted-runners','--no-public-good','--format','json']
 result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if result.returncode:raise ValueError('private GitHub provenance verification failed (gh exit '+str(result.returncode)+')')
 records=json.loads(result.stdout)
 if not records:raise ValueError('no verified private attestation')
 for record in records:
  certificate=record['verificationResult']['signature']['certificate']
  # Only certificate identity is issuer-authenticated; never trust a predicate's claimed run.
  invocation=certificate.get('runInvocationURI','')
  parsed=urlsplit(invocation)
  parts=parsed.path.strip('/').split('/')
  if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.query or parsed.fragment or parts[:4]!=PRIVATE.split('/')+['actions','runs'] or len(parts)!=7 or parts[5]!='attempts':continue
  if parts[4]==str(m['run_id']) and positive(parts[6])>=positive(m['run_attempt']):return m,seal
 raise ValueError('signed private run id/attempt does not match the manifest')


def output(values):
 file=os.environ.get('GITHUB_OUTPUT')
 if file:
  with open(file,'a') as stream:
   for key,value in values.items():stream.write(key+'='+str(value)+'\n')

def summary(message):
 file=os.environ.get('GITHUB_STEP_SUMMARY')
 if file:
  with open(file,'a') as stream:stream.write(message+'\n')
