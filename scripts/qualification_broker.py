"""Trusted writer/worker coordination. No candidate executable runs here."""
import json,os,subprocess,time
from pathlib import Path
from release_policy import API,CONFIG,PUBLIC,positive,digest,summary,validate_files
WORKFLOW='.github/workflows/qualify-platforms.yml'
PLATFORMS={'Qualify macos-arm64','Qualify macos-x64','Qualify linux-x64','Qualify linux-arm64','Qualify windows-x64'}

def validate_qualification(run,jobs,source_sha,throwaway):
 if run.get('path','').split('@',1)[0]!=WORKFLOW or run.get('head_branch')!=CONFIG['branch'] or run.get('head_sha')!=source_sha or run.get('event')!='repository_dispatch' or run.get('status')!='completed':raise ValueError('foreign or incomplete public qualification run')
 for name in {'candidate'}|PLATFORMS:
  matches=[j for j in jobs if j['name']==name]
  if len(matches)!=1 or matches[0]['status']!='completed' or matches[0]['conclusion']!='success':raise ValueError('required native qualification did not pass: '+name)
 control=[j for j in jobs if j['name']=='deliberate-failure-test']
 if len(control)!=1:raise ValueError('missing deliberate-test result')
 expected='failure' if throwaway else 'skipped'
 if control[0]['conclusion']!=expected or run.get('conclusion')!=('failure' if throwaway else 'success'):raise ValueError('unexpected failure/control result')

def jobs(api,run_id):
 out=[];page=1
 while True:
  data=api.request('actions/runs/'+str(run_id)+'/jobs?per_page=100&page='+str(page));out+=data['jobs']
  if len(data['jobs'])<100:return out
  page+=1

def broker():
 api=API();root=Path('draft-assets');manifest,seal=validate_files(root)
 parent=positive(os.environ['GITHUB_RUN_ID']);attempt=positive(os.environ['GITHUB_RUN_ATTEMPT']);artifact=positive(os.environ['ARTIFACT_ID']);artifact_digest=os.environ['ARTIFACT_DIGEST'];tag=manifest['tag']
 title=f'Qualify artifact {parent}.{attempt} {tag}'
 api.request('dispatches',method='POST',data={'event_type':CONFIG['product']+'-qualify-frozen','client_payload':{'parent_run_id':parent,'parent_attempt':attempt,'artifact_id':artifact,'artifact_digest':artifact_digest,'tag':tag}})
 summary('Read-only public qualification requested for parent '+str(parent)+', artifact '+str(artifact)+'.')
 # Actions dispatch is asynchronous and returns no run id. This is queue-state
 # observation, not mock behavior or a release deadline/budget.
 while True:
  matches=[];page=1
  while True:
   batch=api.request('actions/workflows/qualify-platforms.yml/runs?event=repository_dispatch&head_sha='+os.environ['GITHUB_SHA']+'&per_page=100&page='+str(page))['workflow_runs']
   matches += [r for r in batch if r.get('display_title')==title]
   if len(batch)<100:break
   page+=1
  if len(matches)>1:raise ValueError('ambiguous public qualification correlation')
  if matches:break
  time.sleep(3)
 run_id=matches[0]['id'];summary('Qualification run: https://github.com/'+PUBLIC+'/actions/runs/'+str(run_id));print('Waiting for credential-free qualification run '+str(run_id),flush=True)
 result=subprocess.run(['gh','run','watch',str(run_id),'--repo',PUBLIC,'--exit-status'])
 run=api.request('actions/runs/'+str(run_id));validate_qualification(run,jobs(api,run_id),os.environ['GITHUB_SHA'],manifest['deliberate_failure'])
 mode='cleanup' if manifest['deliberate_failure'] else 'promote'
 request=json.loads((root/'candidate-request.json').read_text())
 env=dict(os.environ,DRAFT_TAG=tag,SEAL_ASSET_ID=str(request['seal_asset_id']),BUNDLE_ASSET_ID=str(request['bundle_asset_id']),FREEZE_SHA=request['seal_sha256'],QUALIFICATION_RUN_ID=str(run_id))
 subprocess.run(['python3','scripts/manage-qualified-draft.py',mode,str(root)],env=env,check=True)
 if manifest['deliberate_failure']:raise SystemExit('Deliberate public qualification failure proved; only the sealed throwaway was revoked and cleaned.')
 if result.returncode:raise ValueError('watch reported failure despite successful qualification API state')

if __name__=='__main__':
 try:broker()
 except (ValueError,KeyError,OSError) as error:summary('Qualification/publication refused: '+str(error));raise SystemExit(str(error))
