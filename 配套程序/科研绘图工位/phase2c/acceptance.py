"""Read-only acceptance of native reports against approved values and stable group IDs."""
from pathlib import Path
import json,numpy as np,pandas as pd
from figure_system.common import read,sha,write_new
from .semantics import validate,validate_render_plan,validate_style_owner

def inspect_bundle(bundle,color_codes,bar_geometry=None):
 bundle=Path(bundle);c=read(bundle/'PLOT_SEMANTICS_CONTRACT.json');s=read(bundle/'figure_spec.json')
 validate(c,bundle);validate_render_plan(c,s,bundle);validate_style_owner(c,s)
 frame=pd.read_csv(bundle/'plot_data.csv',float_precision='round_trip');checks={};fail=[]
 def ck(name,ok):
  checks[name]=bool(ok)
  if not ok:fail.append(name)
 for label,path in [('fresh',bundle/'origin_render_report.json'),('reopen',bundle/'independent_reopen/reopen_report.json')]:
  if not path.exists():ck(label+'_native_report',False);continue
  r=read(path)['readback']
  if r.get('matrix'):
   expected=frame[[v['y'] for v in s['series']]].to_numpy(dtype=float)
   ck(label+'_approved_matrix',np.allclose(r['matrix']['data'],expected,rtol=0,atol=1e-12))
   ck(label+'_color_scale',r.get('color_scale',{}).get('label_pt')==s['tokens']['tick_pt'] and r.get('color_scale',{}).get('show')==1)
  for p in ([] if r.get('matrix') else r['plots']):
   b=p['binding']
   if b is None:ck(label+'_binding_'+str(p['index']),False);continue
   expected=frame[b['column']].dropna().to_numpy(dtype=float)
   actual=np.array([v for v in b['values'] if v is not None],dtype=float)
   ck(label+'_approved_y_'+str(p['index']),actual.shape==expected.shape and np.allclose(actual,expected,rtol=0,atol=1e-12))
   if b['x_values'] is not None:
    ex=frame[b['x_column']].dropna().to_numpy(dtype=float);ac=np.array([v for v in b['x_values'] if v is not None],dtype=float)
    ck(label+'_true_x_'+str(p['index']),ac.shape==ex.shape and np.allclose(ac,ex,rtol=0,atol=1e-12))
   ck(label+'_group_color_'+str(p['index']),p['properties']['color']==color_codes[s['all_groups'][b['group_id']]['edge']])
   if c.get('dense_sampling'):ck(label+'_line_only_'+str(p['index']),p['pid']==200)
   if c['connection']['mode']=='ecdf':ck(label+'_right_continuous_ecdf_'+str(p['index']),p['properties'].get('line_connection')==11)
  for axis in ('x','y'):
   actual=r['axes'][axis];target=s[axis+'_limits']
   ck(label+'_axis_limits_'+axis,abs(actual['from']-target[0])<1e-8 and abs(actual['to']-target[1])<1e-8)
  if s['x_scale']=='log10':ck(label+'_log10_x',r['axes']['x']['type']==2)
 if c['selected_archetype']=='bar_raw' and bar_geometry is None:
  import pymupdf
  for label,folder in [('fresh',bundle),('reopen',bundle/'independent_reopen')]:
   files=list(folder.glob('*.pdf'))
   if not files:ck(label+'_filled_native_bars',False);continue
   with pymupdf.open(files[0]) as doc:
    drawings=doc[0].get_drawings()
    fresh=read(bundle/'origin_render_report.json')['readback'];t=s['tokens']
    for series in (v for v in s['series'] if v['role']=='group_summary'):
     xpos=float(frame.loc[frame[series['y']].notna(),series['x']].iloc[0])
     cx=t['width_mm']*72/25.4*(t['layer_left_percent']/100+t['layer_width_percent']/100*(xpos-s['x_limits'][0])/(s['x_limits'][1]-s['x_limits'][0]))
     count=sum(1 for d in drawings if d['fill'] is not None and abs((d['rect'].x0+d['rect'].x1)/2-cx)*25.4/72<1 and d['rect'].width*25.4/72>.5 and d['rect'].height*25.4/72>10)
     ck(label+'_filled_native_bar_'+series['group_id'],count>=1)
    bars=[v for v in fresh['plots'] if v['pid']==203]
    ck(label+'_raw_values_visually_distinguished',all(v['properties']['transparency']>=65 for v in bars))
 if c['selected_archetype']=='bar_raw' and bar_geometry is not None:
  geometry=bar_geometry(bundle)
  for name,ok in geometry['checks'].items():ck(name,ok)
 else:geometry=None
 report={'pass':not fail,'failures':fail,'checks':checks,'contract_sha256':sha(bundle/'PLOT_SEMANTICS_CONTRACT.json'),'analysis_sha256':sha(bundle/'analysis_manifest.json'),'does_not_recompute_statistics':True,'bar_geometry_scope':'This frozen bar fixture only; missing filled drawing match is not proof of absent bars, especially with Origin transparency forms','validator_sha256':sha(Path(__file__)), 'validation_schema_version':3}
 report['bar_native_vector_png_evidence']=geometry
 report['validation_schema_version']=4 if bar_geometry else 3
 write_new(bundle/('NATIVE_SEMANTICS_ACCEPTANCE.v4.json' if bar_geometry else 'NATIVE_SEMANTICS_ACCEPTANCE.v3.json'),report);return report
