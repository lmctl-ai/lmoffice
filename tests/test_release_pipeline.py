"""Offline release regression controls. No network, actual tokens or release mutation."""
import hashlib,json,os,runpy,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def text(file):return (ROOT/file).read_text()

def job_blocks():
 data={};current=None
 for line in text('.github/workflows/qualify-private-draft.yml').split('\njobs:\n',1)[1].splitlines():
  if line.startswith('  ') and not line.startswith('   ') and line.endswith(':'):
   current=line.strip()[:-1];data[current]=[]
  elif current:data[current].append(line)
 return {key:'\n'.join(value) for key,value in data.items()}

class CredentialBoundary(unittest.TestCase):
 def test_only_final_promoter_has_contents_write(self):
  jobs=job_blocks();writers={name for name,body in jobs.items() if 'contents: write' in body}
  self.assertEqual(writers,{'promote'})
 def test_candidate_execution_has_no_token_environment(self):
  action=text('.github/actions/qualify-platform/action.yml')
  self.assertNotIn('GH_TOKEN:',action);self.assertNotIn('GITHUB_TOKEN:',action)
  self.assertIn('persist-credentials: false',text('.github/workflows/qualify-private-draft.yml'))
 def test_installed_candidate_cannot_see_parent_token(self):
  with tempfile.TemporaryDirectory() as directory:
   d=Path(directory);candidate=d/'assets';candidate.mkdir();tools=d/'tools';tools.mkdir();record=d/'observed.json'
   host=("#!"+sys.executable+"\nimport os,json,pathlib\npathlib.Path("+repr(str(record))+").write_text(json.dumps({'credential':bool(os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))}))\nprint('lmoffice 1.2.3')\n").encode()
   (candidate/'lmoffice-linux-x64').write_bytes(host)
   (candidate/'SHA256SUMS').write_text(hashlib.sha256(host).hexdigest()+'  lmoffice-linux-x64\n')
   (candidate/'RELEASE-MANIFEST.json').write_text(json.dumps({'tag':'v1.2.3','version':'1.2.3'}))
   compiler=tools/'compiler';compiler.write_text('#!'+sys.executable+"\nimport os,pathlib\nprint('source: PATH')\nprint('path: '+str(pathlib.Path(os.environ['RUNNER_TEMP'])/'lmoffice-draft-bin/lmoffice'))\n");compiler.chmod(0o755)
   env={'PATH':'/usr/bin:/bin','RUNNER_TEMP':str(d),'GITHUB_ENV':str(d/'env'),'GITHUB_PATH':str(d/'path'),'GH_TOKEN':'SYNTHETIC_ONLY','GITHUB_TOKEN':'SYNTHETIC_ONLY'}
   r=subprocess.run([sys.executable,str(ROOT/'scripts/install-draft-host.py'),'--compiler',str(compiler),'--tag','v1.2.3','--asset','lmoffice-linux-x64','--candidate',str(candidate)],env=env,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertFalse(json.loads(record.read_text())['credential'])
 def test_documented_permissions_match_workflow(self):
  doc=text('docs/release-pipeline.md');declared={}
  for line in doc.splitlines():
   if not line.startswith('|'):continue
   cells=[x.strip().strip('`') for x in line.strip('|').split('|')]
   if len(cells)>=2 and cells[0] in job_blocks():declared[cells[0]]=cells[1]
  actual={name:('contents:write' if 'contents: write' in body else 'contents:read') for name,body in job_blocks().items()}
  self.assertEqual(declared,actual)
 def test_actions_pinned(self):
  for f in ['.github/workflows/qualify-private-draft.yml','.github/workflows/public-ci.yml','.github/actions/qualify-platform/action.yml']:
   for line in text(f).splitlines():
    if 'uses:' not in line:continue
    ref=line.split('uses:',1)[1].split('#',1)[0].strip()
    if ref.startswith('./'):continue
    pin=ref.rsplit('@',1)[-1]
    self.assertEqual(len(pin),40,(f,ref));self.assertTrue(all(c in '0123456789abcdef' for c in pin))
 def test_cancel_guard(self):
  body=job_blocks()['promote'];line=next(l for l in body.splitlines() if l.strip().startswith('if:'))
  self.assertIn('!cancelled()',line)
 def test_candidate_queue_does_not_drop_other_versions(self):
  workflow=text('.github/workflows/qualify-private-draft.yml')
  group=next(l for l in workflow.splitlines() if l.strip().startswith('group:'))
  self.assertIn('client_payload.tag',group)
  self.assertIn('queue: max',job_blocks()['promote'])

class SealedPolicy(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.path=ROOT/'scripts/release_policy.py'
  cls.module=runpy.run_path(str(cls.path)) if cls.path.exists() else {}
 def required(self,name):
  self.assertIn(name,self.module,'missing reusable release policy '+name)
  return self.module[name]
 def test_provenance_required(self):
  validate=self.required('validate_manifest')
  with self.assertRaises(ValueError):validate({'format':'lmoffice-release-candidate/1','repository':'lmctl-ai/lmoffice','source_sha':'0'*40})
 def test_older_and_revoked_refused(self):
  check=self.required('allow_promotion')
  with self.assertRaises(ValueError):check('v0.1.20','v0.1.58',[])
  with self.assertRaises(ValueError):check('v0.1.59','v0.1.58',['v0.1.59'])
 def test_cleanup_requires_sealed_throwaway(self):
  check=self.required('allow_cleanup')
  with self.assertRaises(ValueError):check({'deliberate_failure':False})
 def test_changed_asset_identity_refused(self):
  check=self.required('same_assets')
  with self.assertRaises(ValueError):check([{'id':1,'name':'a','digest':'sha256:aa','size':2}],[{'id':2,'name':'a','digest':'sha256:aa','size':2}])
 def test_private_attestation_verifier_is_required(self):
  verify=text('scripts/verify-draft-candidate.py')
  self.assertIn('verify_attestation',verify)

if __name__=='__main__':unittest.main()
