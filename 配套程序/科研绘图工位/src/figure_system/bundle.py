"""Small bundle orchestration. FileLock/no-clobber rename own concurrency and publication."""
import sys,os,re,shutil,subprocess,tempfile
from pathlib import Path
from filelock import FileLock
from .common import ROOT,ORIGIN_PY,read,sha,write_new,now,require_hash
from .state import resolve
from .qa import inspect_exports,check_native
from .persistence import compare_native_and_rendered

def safe_name(name):
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',name):raise ValueError('invalid edition name')
 return name

def check_existing(path):
 path=Path(path)
 if not path.exists():return
 m=path/'artifact_manifest.json'
 if not m.is_file():raise FileExistsError('CONFLICT / unknown-manual-change: unmanifested existing directory')
 for f,h in read(m)['artifacts'].items():
  p=path/f
  if not p.is_file() or sha(p)!=h:raise FileExistsError('CONFLICT / unknown-manual-change: '+f)
 raise FileExistsError('immutable existing edition; choose a new edition name')

def worker(action,out):
 env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(ROOT/'temp'),TMP=str(ROOT/'temp'))
 log=out/'worker.log'
 with log.open('x',encoding='utf-8') as f:
  run=subprocess.run([str(ORIGIN_PY),str(ROOT/'scripts/origin_worker.py'),action,str(out)],stdout=f,stderr=subprocess.STDOUT,env=env,timeout=240)
 if run.returncode:raise RuntimeError('Origin worker failed; see '+str(log))

def render_bundle(figure,version,edition,groups=None):
 edition=safe_name(edition);dest=ROOT/'artifacts/bundles'/edition;dest.parent.mkdir(parents=True,exist_ok=True)
 with FileLock(str(ROOT/'artifacts/.writer.lock')):
  check_existing(dest);out=Path(tempfile.mkdtemp(prefix=edition+'-',dir=ROOT/'temp'))
  try:
   spec=resolve(figure,version,groups);write_new(out/'figure_spec.json',spec)
   for src,dst in [(spec['source_path'],'source.csv'),(spec['summary_path'],'approved_summary.csv'),(spec['analysis_path'],'analysis_manifest.json'),(ROOT/'fixtures/styles'/f'{version}.json','figurestate.json')]:shutil.copyfile(src,out/dst)
   for semantic_file in (ROOT/'phase2c/legacy_contracts'/figure).iterdir():
    if semantic_file.is_file():shutil.copyfile(semantic_file,out/semantic_file.name)
   worker('render',out)
   stem=f'{figure}.generated.{version}';project=out/(stem+'.opju')
   reopen=out/'independent_reopen';reopen.mkdir();write_new(reopen/'request.json',{'mode':'reopen','bundle':str(out),'project':str(project),'project_sha256':sha(project)})
   worker('inspect',reopen)
   q=inspect_exports(out/(stem+'.pdf'),out/(stem+'.svg'),spec);n=check_native(spec,read(out/'origin_render_report.json'));rn=check_native(spec,read(reopen/'reopen_report.json'))
   q.update(native=n,independent_reopen=rn)
   saved=read(out/'origin_render_report.json')['readback'];opened=read(reopen/'reopen_report.json')['readback']
   q['native_persistence']={'all_equal':saved==opened,'changed_fields':[k for k in saved if saved[k]!=opened[k]],'assessment':compare_native_and_rendered(saved,opened,out,reopen)}
   if not q['native_persistence']['assessment']['pass']:q['status']='FAILED';q['failures'].append('native_persistence')
   write_new(out/'QA_REPORT.json',q)
   if q['status']!='AUTOMATED PASS' or n['status']!='NATIVE PASS' or rn['status']!='NATIVE PASS':raise RuntimeError('QA gate failed: '+str(q['failures']+n['failures']+rn['failures']))
   for name in [stem+'.opju',stem+'.svg',stem+'.pdf','source.csv','approved_summary.csv','figure_spec.json','analysis_manifest.json','QA_REPORT.json']:
    if not (out/name).is_file() or not (out/name).stat().st_size:raise RuntimeError('missing required artifact: '+name)
   hashes={str(p.relative_to(out)).replace('\\','/'):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
   manifest={'schema_version':1,'manuscript_id':spec['manuscript_id'],'figure_id':figure,'style_version':version,'group_registry_version':spec['group_registry_version'],'source_sha256':spec['source_sha256'],'analysis_sha256':spec['analysis_sha256'],'backend':spec['backend'],'backend_version':'EditaPlot 01721038 + isolated table-plan patch','environment':read(out/'environment_report.json'),'template':spec['template'],'theme':spec['theme'],'requested_mm':[spec['tokens']['width_mm'],spec['tokens']['height_mm']],'actual_mm':q['actual_mm'],'actual_opju_mm':read(out/'origin_render_report.json')['readback']['actual_page_mm'],'artifacts':hashes,'created_at':now(),'status':'COMPLETE_AUTO_NATIVE','visual_review':'PENDING','human_accepted':False,'staging_path_at_creation':str(out)}
   write_new(out/'artifact_manifest.json',manifest);os.rename(out,dest);print('BUNDLE',dest,flush=True);return dest
  except Exception as exc:
   if not (out/'transaction_failure.json').exists():write_new(out/'transaction_failure.json',{'status':'FAILED','error':str(exc),'intended_destination':str(dest),'created_at':now()})
   if not (out/'artifact_manifest.json').exists():
    write_new(out/'artifact_manifest.json',{'schema_version':1,'status':'FAILED','error':str(exc),'manuscript_id':spec['manuscript_id'] if 'spec' in locals() else None,'figure_id':figure,'style_version':version,'group_registry_version':spec['group_registry_version'] if 'spec' in locals() else None,'backend':'Origin/EditaPlot','backend_version':'01721038 + isolated table-plan patch','environment':read(out/'environment_report.json') if (out/'environment_report.json').exists() else 'UNVERIFIED','template':spec['template'] if 'spec' in locals() else None,'theme':spec['theme'] if 'spec' in locals() else None,'requested_mm':[spec['tokens']['width_mm'],spec['tokens']['height_mm']] if 'spec' in locals() else None,'actual_mm':q['actual_mm'] if 'q' in locals() else 'UNVERIFIED','actual_opju_mm':read(out/'origin_render_report.json')['readback']['actual_page_mm'] if (out/'origin_render_report.json').exists() else 'UNVERIFIED','source_sha256':spec['source_sha256'] if 'spec' in locals() else None,'analysis_sha256':spec['analysis_sha256'] if 'spec' in locals() else None,'artifacts':{str(p.relative_to(out)).replace('\\','/'):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},'created_at':now(),'human_accepted':False})
   print('FAILED_STAGING',out,flush=True);raise

def register_manual(bundle,edited_path,edition,creator='AUTHOR_DECLARED'):
 bundle=Path(bundle);m=read(bundle/'artifact_manifest.json');spec=read(bundle/'figure_spec.json');stem=f"{spec['figure_id']}.generated.{spec['style_version']}.opju";parent=bundle/stem;require_hash(parent,m['artifacts'][stem])
 target=ROOT/'artifacts/manual'/safe_name(edition);target.parent.mkdir(parents=True,exist_ok=True)
 with FileLock(str(ROOT/'artifacts/.writer.lock')):
  if target.exists():raise FileExistsError('manual edition exists; never overwritten')
  stage=Path(tempfile.mkdtemp(prefix='manual-',dir=ROOT/'temp'));filename=f"{spec['figure_id']}.manual.{spec['style_version']}.1.opju";shutil.copyfile(edited_path,stage/filename)
  write_new(stage/'manual_manifest.json',{'parent_generated_artifact':str(parent),'parent_sha256':sha(parent),'created_at':now(),'style_version':spec['style_version'],'source_sha256':spec['source_sha256'],'analysis_sha256':spec['analysis_sha256'],'parent_verification_status':m['status'],'manual_status':'REGISTERED_PRESERVED','creator':creator,'artifact':filename,'sha256':sha(stage/filename),'human_accepted':False});os.rename(stage,target);return target
