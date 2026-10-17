"""Small extensions of Phase 2C's renderer; no lifecycle/export/statistics engine."""
from pathlib import Path
from dataclasses import replace
import json,math
from xml.etree import ElementTree as ET
from figure_system.common import ROOT,read,write_new
from phase2c import native as base
from origin_sciplot.origin_backend import scientific_renderer as renderer
_original_apply=base.apply_b
_original_table=base.table
_original_inspect=base.inspect_native
_original_prepare=base.prepare
_nested_displays={}
def prepare(spec,out):
 frame,style,prep=_original_prepare(spec,out)
 mapping=spec.get('native_display_labels')
 if mapping:
  approved=read(out/'analysis_manifest.json')['approved_display_labels']
  assert mapping==approved
  series=tuple(replace(s,label=mapping[s.source_column]) for s in prep.plot_spec.series)
  prep=replace(prep,plot_spec=replace(prep.plot_spec,series=series))
 return frame,style,prep
def table(spec,frame):
 plan=_original_table(spec,frame)
 if spec.get('figure_id')!='nested_overlay':return plan
 display=_nested_displays[spec['figure_id']]
 series=[]
 for old,source in zip(plan.series,spec['series']):
  if source['role']=='subsamples':old=replace(old,marker_size_pt=display['secondary_marker_pt'],transparency_percent=display['secondary_transparency_percent'])
  if source['role']=='unit_summary':old=replace(old,marker_size_pt=display['primary_marker_pt'],transparency_percent=0)
  series.append(old)
 return replace(plan,series=tuple(series))
def colorscale_format(op,path,set_font,pt):
 path=Path(path)
 assert not path.exists(), 'Immutable Color Scale readback already exists'
 code=ROOT/'phase2c_1/colorscale_format.c'
 assert op.lt_exec(f'__p2cCompile=run.LoadOC("{code}");')
 assert op.lt_float('__p2cCompile')==0, 'Native Color Scale helper compile failed'
 assert op.lt_exec(f'__p2cFormat=p2c1_colorscale_format("{path}",{int(set_font)},{pt:g});')
 assert op.lt_float('__p2cFormat')==1, 'Native Color Scale format failed'
 root=ET.parse(path).getroot();axis=root.find('Root/DimAxes/DimAxis2/NewAxes/NewAxis1')
 return {'title_pt':float(axis.findtext('Title/Font/Size')),
  'title_font_face':int(axis.findtext('Title/Font/Face')),
  'label_font_face':int(axis.findtext('Labels/MajorLabels/Font/Face'))}
def apply(op,graph,spec,prep):
 _original_apply(op,graph,spec,prep);layer=graph[0];graph.activate()
 if spec['x_scale']=='log10':
  # Native Log10 remains type=2. Documented decimal numeric tick format avoids
  # the native scientific-notation superscript glyph issue; no string replacement.
  layer.set_int('x.label.type',1);layer.set_int('x.label.numFormat',1);layer.set_int('x.label.decPlaces',-1)
  layer.set_float('x.label.pt',spec['tokens']['tick_pt'])
  layer.axis('x').set_limits(*spec['x_limits'])
 if spec.get('time_axis_mode')=='CATEGORICAL_SCHEDULE':
  labels=op.new_sheet('w',lname='Approved equal-spaced sampling schedule')
  labels.from_list(0,read(Path(prep.source_path).parent/'PLOT_SEMANTICS_CONTRACT.json')['time_axis']['schedule_h'])
  labels.from_list(1,__import__('pandas').read_csv(prep.source_path)['Schedule'].tolist())
  graph.activate();assert op.lt_exec(f'range __p2c1Schedule={labels.lt_range(False)}!col(2);axis -ps X T __p2c1Schedule;')
  layer.axis('x').set_limits(*spec['x_limits'])
 if spec['backend_route']=='heatmap':
  # All properties are official native Color Scale properties, applied after sizing.
  assert op.lt_exec('spectrum1.title=1;spectrum1.title$="Signal (a.u.)";spectrum1.labels.fsize=7;spectrum1.labels.bold=0;')
  colorscale_format(op,Path(prep.source_path).parent/'colorscale_format_applied.xml',True,spec['tokens']['axis_title_pt'])
  assert op.lt_exec('spectrum1.labels.numdisp=1;spectrum1.labels.decplaces=2;spectrum1.height=page.height*.64;spectrum1.barthick=100;spectrum1.left=page.width*.835;spectrum1.top=page.height*.16;')
 if spec.get('figure_id')=='nested_overlay':
  legend=layer.label('legend')
  legend.text += '\n'+r'\L(1) Field subsamples (secondary)'
  op.lt_exec('doc -uw;legend.left=page.width*.18;legend.top=page.height*.04;')
  # Preserve B grammar: same Arial 7 pt, only native symbol geometry changes by role.
 op.lt_exec('doc -uw;')
def inspect(op,graph,spec,out,source_sheet,mapping=None):
 report=_original_inspect(op,graph,spec,out,source_sheet,mapping)
 if spec['backend_route']=='heatmap':
  graph.activate();report['color_scale']={k:float(op.lt_float('spectrum1.'+v)) for k,v in {
   'label_pt':'labels.fsize','show':'show','title_show':'title','left':'left','top':'top','width':'width','height':'height','thickness':'barthick'}.items()}
  report['color_scale']['title']=op.get_lt_str('spectrum1.title')
  path=out/'colorscale_native_readback.xml'
  if path.exists():path=out/'independent_reopen/colorscale_native_readback.xml'
  report['color_scale'].update(colorscale_format(op,path,False,spec['tokens']['axis_title_pt']))
  assert report['color_scale']['title_pt']==spec['tokens']['axis_title_pt']
  assert report['color_scale']['title_font_face']==report['color_scale']['label_font_face']
  assert report['color_scale']['label_pt']==spec['tokens']['tick_pt']
  assert report['color_scale']['show']==1 and report['color_scale']['title_show']==1
 if spec.get('time_axis_mode'):report['time_axis_mode']=spec['time_axis_mode']
 return report
def probe(op,out):
 p=ROOT/'phase2c/runs/20261007_200635/heatmap/diagnostic_native'
 assert op.open(str(next(p.glob('*.opju'))));graph=op.find_graph();graph.activate();layer=graph[0];rows=[]
 for cmd in ('spectrum1.labels.fsize=7;','spectrum1.width=page.width*.09;','spectrum1.height=page.height*.75;','spectrum1.labels.fsize=7;'):
  before=op.lt_float('spectrum1.labels.fsize');ok=op.lt_exec(cmd);op.lt_exec('doc -uw;')
  rows.append({'command':cmd,'before':before,'after':op.lt_float('spectrum1.labels.fsize'),'execute':bool(ok)})
 print(rows,flush=True);write_new(out/'probe_report.json',{'rows':rows})
 graph.save_fig(str(out/'probe.png'),type='png',width=1052)
def dispatch(op,action,out):
 if action=='phase2c1-probe':return probe(op,out)
 if action=='phase2c1-color-title-probe':
  from .color_title_probe import run
  return run(op,out)
 from .contracts import validate_target
 if action=='phase2c1-render':
  for path in read(out/'batch_request.json')['bundles']:
   validate_target(path)
   spec=read(Path(path)/'figure_spec.json')
   if spec['figure_id']=='nested_overlay':
    _nested_displays[spec['figure_id']]=read(Path(path)/'analysis_manifest.json')['approved_nested_display']
 from origin_sciplot.origin_backend import categorical_renderer as cr
 upstream_layout=cr.resolve_heatmap_layout
 def manuscript_layout(**kwargs):
  layout=upstream_layout(**kwargs)
  # Upstream uses a >=15pt preview default; B manuscript colorbar is 7pt.
  return replace(layout,colorbar_label_size_pt=kwargs['tick_label_size_pt'],cell_label_size_pt=kwargs['tick_label_size_pt'])
 cr.resolve_heatmap_layout=manuscript_layout
 base.apply_b=apply;base.inspect_native=inspect;base.prepare=prepare
 base.table=table
 base.batch(op,action.replace('phase2c1-','phase2c-'),out)




