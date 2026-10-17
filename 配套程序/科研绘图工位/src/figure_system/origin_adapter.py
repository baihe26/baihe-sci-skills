"""Thin composition over EditaPlot's real renderer/models and official originpro."""
import sys,json,csv
from pathlib import Path
from dataclasses import replace,fields
from .common import ROOT,EDITAPLOT,sha,require_hash,write_new
sys.path.insert(0,str(EDITAPLOT/'runtime/src'))
import numpy as np
import pandas as pd
from origin_sciplot.scientific_visual import AdaptiveOriginStyle
from origin_sciplot.scientific_workflow import ScientificSeries,ScientificAxisPlan,ScientificDisplayPlan,ScientificPlotSpec,ScientificPreparation,evidence_jitter_offsets
from origin_sciplot.origin_backend import scientific_renderer as renderer
from origin_sciplot.origin_backend.evidence_renderer import _read_shap_plot_binding
from origin_sciplot.origin_backend.export_utils import export_graph
from origin_sciplot.output_manager import RunOutput
SYMBOL={'circle':2,'square':1,'triangle':3}
LINE={'solid':0,'dash':1,'dot':2}

def output_paths(out,spec):
 stem=f"{spec['figure_id']}.generated.{spec['style_version']}"
 d={f.name:out/(f.name+'.json') for f in fields(RunOutput)}
 d.update(output_dir=out,input_copy=out/'plot_data.csv',render_plan_copy=out/'figure_spec.json',result_opju=out/(stem+'.opju'),result_png=out/(stem+'.png'),result_pdf=out/(stem+'.pdf'),result_tif=out/(stem+'.tif'))
 return RunOutput(**d)

def make_plan(spec,out):
 for key,pathkey in [('source_sha256','source_path'),('summary_sha256','summary_path'),('analysis_sha256','analysis_path')]:require_hash(spec[pathkey],spec[key])
 summary=pd.read_csv(spec['summary_path'],float_precision='round_trip')
 t=spec['tokens']; a=spec['figure_id']=='FigA'; xkey='condition' if a else 'time'
 frame=pd.DataFrame({'X':range(1,3) if a else spec['x_order']})
 if a:frame['Condition']=spec['x_order']
 series=[]
 for gid,g in spec['groups'].items():
  rows=summary[summary.group==g['display_name']].set_index(xkey).loc[spec['x_order']]
  frame[gid+'_Mean']=rows['mean'].to_numpy();frame[gid+'_SD']=rows['std'].to_numpy()
  series.append(ScientificSeries(gid+'_Mean',g['display_name'],error_column=gid+'_SD',error_kind='SD',group=gid))
 output=output_paths(out,spec);frame.to_csv(output.input_copy,index=False)
 style=AdaptiveOriginStyle(profile_name=spec['style_version'],page_width_cm=t['width_mm']/10,page_height_cm=t['height_mm']/10,layer_left_percent=t['layer_left_percent'],layer_top_percent=t['layer_top_percent'],layer_width_percent=t['layer_width_percent'],layer_height_percent=t['layer_height_percent'],font_family=t['font_family'],axis_title_size_pt=t['axis_title_pt'],tick_label_size_pt=t['tick_pt'],legend_size_pt=t['legend_pt'],plot_line_width_pt=t['line_width_pt'],frame_line_width_pt=t['axis_width_pt'],major_tick_length_pt=t['tick_length_pt'],minor_tick_length_pt=0,error_bar_width_pt=t['error_width_pt'],fill_transparency_percent=0)
 plot=ScientificPlotSpec(plot_kind='line_error',plot_mode='line_error',x_column='X',category_column='Condition' if a else None,series=tuple(series),x_title=spec['x_title'],y_title=spec['y_title'],y2_title=None,x_scale='linear',y_scale='linear',display_transform='identity',display_plan=ScientificDisplayPlan(t['marker_size_pt'],0.72,0.8,figure_style=style),axis_plan=ScientificAxisPlan(*spec['x_limits'],*spec['y_limits']))
 prep=ScientificPreparation(template_id='line_error',source_path=str(output.input_copy),source_sha256=sha(output.input_copy),source_size_bytes=output.input_copy.stat().st_size,source_format='csv',source_sheet=None,source_columns=tuple(frame.columns),row_count=len(frame),ignored_empty_rows=0,assignments=tuple((c,'x' if c=='X' else 'category' if c=='Condition' else 'error' if c.endswith('_SD') else 'series') for c in frame),plot_spec=plot,confidence=1.0,requires_confirmation=False,confirmation_reasons=(),warnings=('USER_APPROVED_SYNTHETIC_ONLY',),mapping_confirmed=True,plan_digest=sha(out/'figure_spec.json'))
 table=renderer._prepare_origin_table(frame,prep)
 resolved=[]
 for old,(gid,g) in zip(table.series,spec['groups'].items()):
  xcol='X'
  if a:
   xcol=gid+'_DisplayX';table.frame[xcol]=table.frame.X+(g['display_order']-1)*0.24
  resolved.append(replace(old,x_column=xcol,plot_type='s' if a else 'y',color=g['edge'],symbol_kind=SYMBOL[g['marker']],line_style=LINE[g['line_style']],transparency_percent=100*(1-g['alpha']*t['line_alpha'])))
 table=replace(table,series=tuple(resolved),helper_columns=tuple(c for c in table.frame if c not in frame))
 return output,prep,table,frame,style

def plot_command(op,graph,index,command):
 # Stable explicit native graph range: never Plot.index/GetIndex after reopen.
 if not op.lt_exec(f'range __fgp=[{graph.name}]1!{index};set __fgp {command};'):raise RuntimeError('native plot command failed')

def readback(op,graph,spec,mapping):
 graph.activate();layer=graph[0];plots=[]
 for j,m in enumerate(mapping):
  sheet=op.find_sheet('w',m['worksheet'])
  if sheet is None:raise RuntimeError('source worksheet missing')
  # Origin 2024 graph-range Y resolves error parent; native DataPlot name resolves SD.
  parent_y=m['y_column'].replace('_SD','_Mean') if m['role']=='sample_sd' else m['y_column']
  binding=_read_shap_plot_binding(op,layer,f'[{graph.name}]1!{m["index"]}',sheet,m['x_column'],parent_y,prefix=f'fig{j}')
  idx=sheet.lt_col_index(m['y_column'])
  if not op.lt_exec(f'range __fexpected={sheet.lt_range(False)}!col({idx});string __fexpectedname$=nameof(__fexpected)$;'):raise RuntimeError('cannot resolve expected dataset')
  actual_name=list(layer.obj.DataPlots)[m['index']-1].GetName()
  expected_name=op.get_lt_str('__fexpectedname')
  if actual_name!=expected_name:raise RuntimeError(f'native dataset mismatch: {actual_name} != {expected_name}')
  binding['native_dataset']={'actual':actual_name,'expected':expected_name,'equal':True}
  pfx=f'plot{m["index"]}'
  vals={k:float(layer.get_float(pfx+'.'+k)) for k in ['pid','color','symbol.size','transparency']}
  native={}
  for switch,key in [('-c','color'),('-w','width_units'),('-z','size_pt'),('-d','line_style'),('-k','symbol'),('-kf','interior'),('-csf','fill_color')]:
   if m['role']=='sample_sd' and key in ['symbol','interior','fill_color']:continue
   if op.lt_exec(f'range __fgr=[{graph.name}]1!{m["index"]};get __fgr {switch} __fgvalue;'):native[key]=float(op.lt_float('__fgvalue'))
  plots.append({**m,'expected_color':op.ocolor(spec['groups'][m['group_id']]['edge']),'expected_fill':op.ocolor(spec['groups'][m['group_id']]['fill']),'binding':binding,'native':vals,'get':native,'x_values':sheet.to_list(m['x_column']),'y_values':sheet.to_list(m['y_column'])})
 axes={axis:{k:layer.get_float(f'{axis}.{k}') for k in ['from','to','inc','label.pt','thickness','tickthickness','ticks','ticklength','showAxes','showGrids']} for axis in ['x','y']}
 titles={axis:layer.axis(axis).title for axis in ['x','y']}
 legend=layer.label('legend')
 return {'graph':graph.name,'plots':plots,'native_plot_count':len(list(layer.obj.DataPlots)),'axes':axes,'titles':titles,'title_geometry':renderer._title_geometry(op,{'x_title':layer.label('xb'),'y_title':layer.label('yl')}),'legend':{'text':legend.text,'size_pt':legend.get_float('fsize'),'frame':legend.get_int('showframe')} if legend else None,'actual_page_mm':{'width':op.lt_float('page.width/page.resx*25.4'),'height':op.lt_float('page.height/page.resy*25.4')},'api':'EditaPlot binding readback + explicit native LabTalk; no Plot.index after reopen'}

def export_all(op,graph,output):
 exports=export_graph(op,graph,output.result_png,output.result_pdf,output.result_tif,raster_width=1400)
 svg=output.result_opju.with_suffix('.svg');graph.activate()
 if not op.lt_exec(f'expGraph type:=svg export:=page filename:="{svg.stem}" path:="{svg.parent.as_posix()}" overwrite:=replace sysopts:=0 keepsize:=1 tr.Margin:=2;'):raise RuntimeError('SVG export command failed')
 if not svg.is_file() or not svg.stat().st_size:raise RuntimeError('SVG export missing')
 exports['svg']=True;return exports

def render(op,spec,out):
 output,prep,table,frame,style=make_plan(spec,out)
 graph,upstream=renderer._build_origin_graph(op,frame,output,prep,table_plan=table)
 layer=graph[0];summarysheet=next(s for b in op.pages('w') for s in b if table.series[0].plot_column in s.to_df().columns)
 mapping=[]
 for j,(gid,g) in enumerate(spec['groups'].items()):
  main=2*j+1;err=main+1;series=table.series[j]
  for index,role,col in [(main,'mean',series.plot_column),(err,'sample_sd',series.error_column)]:mapping.append({'index':index,'group_id':gid,'role':role,'worksheet':summarysheet.lt_range(False),'x_column':series.x_column,'y_column':col,'expected_count':len(frame)})
  plot_command(op,graph,err,f'-z {spec["tokens"]["error_cap_pt"]}')
  plot_command(op,graph,main,f'-k {SYMBOL[g["marker"]]}')
  plot_command(op,graph,main,'-kf 0');plot_command(op,graph,main,'-paas 1')
  plot_command(op,graph,main,f'-c {op.ocolor(g["edge"])}')
  plot_command(op,graph,main,f'-csf {op.ocolor(g["fill"])}')
 raw=pd.read_csv(spec['source_path'],float_precision='round_trip');raw_evidence=[]
 for j,(gid,g) in enumerate(spec['groups'].items()):
  subset=raw[raw.group==g['display_name']].copy();subset['source_row']=subset.index.to_numpy();subset.reset_index(drop=True,inplace=True)
  if spec['raw_required']:
   xx=[]
   for condition in subset.condition.unique():
    rows=subset[subset.condition==condition]
    xx.extend((spec['x_order'].index(condition)+1+(g['display_order']-1)*0.24+evidence_jitter_offsets(len(rows),g['display_order'])*0.25).tolist())
   subset['DisplayX']=xx
  sheet=op.new_sheet('w',lname='Raw_'+gid);sheet.from_df(subset);sheet.cols_axis()
  roundtrip=sheet.to_df()
  for col in raw.columns:
   exp=subset[col].tolist();actual=roundtrip[col].tolist()
   if pd.api.types.is_numeric_dtype(subset[col]):assert np.allclose(actual,exp,rtol=0,atol=1e-12)
   else:assert list(map(str,actual))==list(map(str,exp))
  raw_evidence.append({'group_id':gid,'worksheet':sheet.lt_range(False),'rows':len(subset),'source_rows':subset.source_row.tolist(),'all_original_columns_equal':True,'numeric_values_equal':True})
  if spec['raw_required']:
   before=len(list(layer.obj.DataPlots))
   rawseries=renderer.OriginSeriesPlan('value','value','DisplayX',None,g['display_name']+' raw','left','s',g['edge'],None,spec['tokens']['raw_marker_size_pt'],symbol_kind=SYMBOL[g['marker']],transparency_percent=100*(1-spec['tokens']['raw_alpha']*g['alpha']))
   renderer._add_plot(layer,sheet,rawseries,'DisplayX',style)
   idx=before+1;plot_command(op,graph,idx,'-kf 0');plot_command(op,graph,idx,'-paas 1');plot_command(op,graph,idx,f'-csf {op.ocolor(g["fill"])}')
   mapping.append({'index':idx,'group_id':gid,'role':'raw','worksheet':sheet.lt_range(False),'x_column':'DisplayX','y_column':'value','expected_count':len(subset)})
 graph.activate();t=spec['tokens']
 # Origin's layer frame is independent of axis visibility (layer -b f).
 if t['frame']=='left_bottom':op.lt_exec('layer -b f 0;')
 for axis in ['x','y']:
  layer.set_int(f'{axis}.showAxes',3 if t['frame']=='box' else 1);layer.set_int(f'{axis}.ticks',2)
  layer.set_int(f'{axis}.minorTicks',0);layer.set_float(f'{axis}.tickthickness',t['tick_width_pt'])
  label=layer.label('xb' if axis=='x' else 'yl');label.text=spec[axis+'_title'];label.set_int('bold',int(t['axis_title_bold']));label.set_float('fsize',t['axis_title_pt'])
 legend=layer.label('legend');legend.text='    '.join(rf'\L({2*j+1}) {g["display_name"]}' for j,g in enumerate(spec['groups'].values()))
 op.lt_exec('legend.attach=1;legend.left=page.width*0.18;legend.top=page.height*0.04;')
 op.lt_exec(f'label -n panel {spec["figure_id"][-1]};panel.attach=1;panel.left=page.width*0.02;panel.top=page.height*0.035;panel.fsize={t["panel_label_pt"]};panel.bold=1;panel.font=font(Arial);')
 layer.label('panel').set_int('font',renderer._origin_font_code(op,t['font_family']))
 op.lt_exec('doc -uw;')
 renderer._position_axis_titles_on_page(op,layer,{'x_title':layer.label('xb'),'y_title':layer.label('yl')})
 op.lt_exec('doc -uw;')
 native=readback(op,graph,spec,mapping)
 if not op.save(str(output.result_opju)):raise RuntimeError('OPJU save failed')
 exports=export_all(op,graph,output)
 report={'status':'ORIGIN VERIFIED','scope':'generated native objects; independent reopen still pending','upstream':upstream,'readback':native,'source_worksheets':raw_evidence,'exports':exports,'mapping':mapping}
 write_new(out/'origin_render_report.json',report)
 return report
