"""Replay the exact unsigned v1 review attacks without calling any network API.
These tests also run unchanged against the old manager for failing controls.
"""
import contextlib,hashlib,io,json,os,runpy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
NAMES=['lmoffice-linux-x64','lmoffice-linux-arm64','lmoffice-macos-arm64','lmoffice-macos-x64','lmoffice-windows-x64.exe','LICENSE','THIRD_PARTY_NOTICES.md','RELEASE-MANIFEST.json']

class LegacyAttacks(unittest.TestCase):
 def attack(self,mode):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);blobs={n:('synthetic '+n).encode() for n in NAMES}
   blobs['SHA256SUMS']=''.join(hashlib.sha256(blobs[n]).hexdigest()+'  '+n+'\n' for n in sorted(NAMES)).encode()
   for n,b in blobs.items():(root/n).write_bytes(b)
   digest=hashlib.sha256(blobs['SHA256SUMS']).hexdigest();calls=[]
   assets=[{'id':i,'name':n,'size':len(b),'url':'https://api.github.com/repos/lmctl-ai/lmoffice/releases/assets/'+str(i)} for i,(n,b) in enumerate(blobs.items(),1)]
   release={'id':77,'tag_name':'v0.1.20','draft':True,'target_commitish':'main','assets':assets};latest={'id':88,'tag_name':'v0.1.58','draft':False,'assets':[]}
   def gh(args,**kwargs):
    if '--slurp' in args:return json.dumps([[latest,release]]).encode()
    if args[0].startswith('https://api.github.com/repos/lmctl-ai/lmoffice/releases/assets/'):
     identifier=int(args[0].rsplit('/',1)[1]);return blobs[assets[identifier-1]['name']]
    if '--method' in args:
     verb=args[args.index('--method')+1];calls.append(verb)
     return json.dumps(dict(release,draft=False)).encode() if verb=='PATCH' else b''
    raise AssertionError('unexpected GitHub call')
   module=runpy.run_path(str(ROOT/'scripts/manage-qualified-draft.py'));main=module['main'];main.__globals__['gh']=gh
   with patch.dict(os.environ,{'GITHUB_REPOSITORY':'lmctl-ai/lmoffice'}),patch.object(sys,'argv',['manager',mode,'v0.1.20',digest,str(root)]),contextlib.redirect_stdout(io.StringIO()):
    try:main()
    except (SystemExit,ValueError):pass
   self.assertEqual(calls,[],'unsigned old protocol must never reach a mutation API')
 def test_unsigned_older_candidate_cannot_promote(self):self.attack('promote')
 def test_unsigned_nonthrowaway_candidate_cannot_cleanup(self):self.attack('cleanup')

if __name__=='__main__':unittest.main()
