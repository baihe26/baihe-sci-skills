"""Read-only native identity check; reuse the existing owned worker and official get."""
from pathlib import Path
from figure_system.common import ROOT,read,write_new,sha,require_hash
from figure_system.origin_adapter import SYMBOL
from origin_sciplot.origin_backend.evidence_renderer import _read_shap_plot_binding

def audit(op,out):
 results={}
 for item in read(out/'identity_request.json')['cases']:
  bundle=ROOT/item['bundle'];spec=read(bundle/'figure_spec.json')
  stages={};fail=[]
  for stage,project in item['projects'].items():
   path=ROOT/project['path'];require_hash(path,project['sha256'])
   print('READ_ONLY_OPEN',item['case'],stage,str(path),flush=True)
   assert op.open(str(path),readonly=True,asksave=False),str(path)
   print('READ_ONLY_OPENED',flush=True)
   graph=op.find_graph();assert graph is not None
   graph.activate();layer=graph[0]
   original=read(bundle/('origin_render_report.json' if stage=='fresh' else 'independent_reopen/reopen_report.json'))['readback']
   plots=[]
   for recorded in original['plots']:
    idx=recorded['index'];binding=recorded['binding']
    if binding is None:continue
    expected=spec['all_groups'][binding['group_id']]
    pid=int(layer.get_int(f'plot{idx}.pid'))
    if pid not in (200,201,202,203):continue
    values={}
    keys=[('-k','symbol'),('-kf','interior'),('-csf','fill_color')] if pid in (201,202) else []
    for switch,key in keys:
     assert op.lt_exec(f'range __p2cID=[{graph.name}]1!{idx};get __p2cID {switch} __p2cIDValue;')
     values[key]=float(op.lt_float('__p2cIDValue'))
    if pid in (201,202):
     for key,value in {'symbol':SYMBOL[expected['marker']],'interior':0,'fill_color':op.ocolor(expected['fill'])}.items():
      if values[key]!=value:fail.append(stage+':'+str(idx)+':'+key)
    if pid==203:values['transparency']=float(layer.get_float(f'plot{idx}.transparency'))
    actual_binding=None
    if binding.get('x_column'):
     try:
      sheet=op.find_sheet('w',binding['worksheet'])
      actual_binding=_read_shap_plot_binding(op,layer,f'[{graph.name}]1!{idx}',sheet,binding['x_column'],binding['column'],prefix=f'p2c{idx}')
     except Exception as error:
      actual_binding={'pass':False,'error':str(error)};fail.append(stage+':'+str(idx)+':actual_XY_binding')
    actual_name=list(layer.obj.DataPlots)[idx-1].GetName()
    if actual_name!=recorded['dataset']:fail.append(stage+':'+str(idx)+':dataset')
    plots.append({'index':idx,'pid':pid,'group_id':binding['group_id'],'get':values,'dataset_equal':actual_name==recorded['dataset'],'official_actual_XY_binding':actual_binding})
   require_hash(path,project['sha256'])
   stages[stage]={'project':project,'plots':plots,'project_bytes_unchanged':True}
   write_new(out/(item['case']+'.'+stage+'.json'),stages[stage])
   print('IDENTITY_STAGE_COMPLETE',item['case'],stage,flush=True)
  results[item['case']]={'pass':not fail,'failures':fail,'stages':stages,'read_only':True,'does_not_replace_original_fresh_reopen_export_evidence':True}
 write_new(out/'NATIVE_IDENTITY_RESULTS.json',results)
 print('READ_ONLY_NATIVE_IDENTITY',results.keys(),flush=True)

