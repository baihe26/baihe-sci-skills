"""Real native integration probes; each invocation runs in a separate owned process."""
from pathlib import Path
from dataclasses import replace
import pandas as pd,numpy as np
from .common import read,write_new,require_hash,sha
from .origin_adapter import readback,output_paths,export_all,plot_command

def verify_sources(op,spec,source_reports):
 raw=pd.read_csv(spec['source_path'],float_precision='round_trip');out=[]
 for r in source_reports:
  s=op.find_sheet('w',r['worksheet']);assert s is not None,'missing raw worksheet'
  expected=raw.iloc[r['source_rows']].reset_index(drop=True);actual=s.to_df()
  for c in raw:
   if pd.api.types.is_numeric_dtype(expected[c]):assert np.allclose(expected[c],actual[c],rtol=0,atol=1e-12),c
   else:assert expected[c].astype(str).tolist()==actual[c].astype(str).tolist(),c
  out.append({**r,'all_original_columns_equal':True,'independent_reopen':True})
 return out

def inspect(op,out):
 req=read(out/'request.json');parent=Path(req['bundle']);spec=read(parent/'figure_spec.json');rr=read(parent/'origin_render_report.json')
 spec.update(source_path=str(parent/'source.csv'),summary_path=str(parent/'approved_summary.csv'),analysis_path=str(parent/'analysis_manifest.json'))
 require_hash(req['project'],req['project_sha256']);assert op.open(req['project']),'independent OPJU open failed'
 g=op.find_graph(rr['readback']['graph']);assert g is not None;g.activate();l=g[0]
 before=readback(op,g,spec,rr['mapping']);sources=verify_sources(op,spec,rr['source_worksheets'])
 if req['mode']=='reopen':
  outputs=output_paths(out,spec);export_all(op,g,outputs)
  write_new(out/'reopen_report.json',{'status':'ORIGIN VERIFIED','readback':before,'source_worksheets':sources,'project_sha256':req['project_sha256'],'independent_process':True});return
 if req['mode']=='edit':
  # Freeze styles/axes during data-link experiment; only one mean and one SD cell change.
  base=out/'before';base.mkdir();export_all(op,g,output_paths(base,spec))
  changes=[]
  for role,delta in [('mean',0.4),('sample_sd',0.15)]:
   m=next(p for p in rr['mapping'] if p['role']==role);s=op.find_sheet('w',m['worksheet']);v=s.to_list(m['y_column']);old=v[0];v[0]+=delta;s.from_list(m['y_column'],v)
   changes.append({'worksheet':m['worksheet'],'column':m['y_column'],'row':0,'before':old,'after':v[0],'plot_index':m['index']})
  op.lt_exec('doc -uw;');g.activate();after_data=readback(op,g,spec,rr['mapping']);dataout=out/'data_only';dataout.mkdir();export_all(op,g,output_paths(dataout,spec))
  # New manual fixture: native style operations, no graph reconstruction.
  l.set_float('y.to',6);l.set_float('x.label.pt',6.5);l.axis('x').title=spec['x_title']+' edited'
  l.label('legend').text=l.label('legend').text+' [edit]'
  plot_command(op,g,1,'-k 5');plot_command(op,g,1,'-z 5');plot_command(op,g,1,f'-c {op.ocolor("#009E73")}');plot_command(op,g,1,f'-csf {op.ocolor("#009E73")}');plot_command(op,g,1,'-w 600')
  op.lt_exec('doc -uw;');changed=readback(op,g,spec,rr['mapping'])
  assert changed['axes']['y']['to']==6 and changed['axes']['x']['label.pt']==6.5
  assert changed['titles']['x'].endswith(' edited') and changed['legend']['text'].endswith(' [edit]')
  first=changed['plots'][0]['get'];assert first['symbol']==5 and first['size_pt']==5 and first['color']==op.ocolor('#009E73') and first['fill_color']==op.ocolor('#009E73') and first['width_units']==600
  for change in changes:
   p=next(v for v in after_data['plots'] if v['index']==change['plot_index']);assert abs(p['y_values'][0]-change['after'])<1e-12
  assert before['axes']==after_data['axes'] and before['legend']==after_data['legend']
  project=out/f"{spec['figure_id']}.manual.{spec['style_version']}.1.opju";assert not project.exists();assert op.save(str(project))
  export_all(op,g,replace(output_paths(out,spec),result_opju=project))
  write_new(out/'edit_report.json',{'status':'ORIGIN VERIFIED','mode':'MACHINE_CONTROLLED_EDIT_NOT_AUTHOR_ACCEPTANCE','project':str(project),'project_sha256':sha(project),'before':before,'data_only':after_data,'after':changed,'changes':changes,'source_worksheets':sources,'graph_rebuilt':False});return
 if req['mode']=='verify_edit':
  expected=read(Path(req['edit_report']))['after']
  # Compare the actual persisted properties and bound values, not a mock API.
  differences={k:{'saved':expected[k],'reopened':before[k]} for k in expected if before[k]!=expected[k]}
  write_new(out/'persistence_comparison.json',{'all_equal':not differences,'differences':differences})
  assert all(k=='title_geometry' for k in differences),'native properties or source binding changed after close/reopen'
  export_all(op,g,output_paths(out,spec))
  write_new(out/'edited_reopen_report.json',{'status':'PARTIAL' if differences else 'ORIGIN VERIFIED','all_native_properties_equal':not differences,'core_native_properties_equal':True,'title_geometry_equal':'title_geometry' not in differences,'readback':before,'source_worksheets':sources,'independent_process':True,'saved_edit_sha256':req['project_sha256']});return
 raise ValueError('unsupported inspection mode')
