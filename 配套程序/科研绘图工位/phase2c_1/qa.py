"""Targeted QA composition; Nature's original findings are always preserved."""
import importlib.util,sys,re,copy
from pathlib import Path
import numpy as np
from PIL import Image
import pymupdf
from defusedxml import ElementTree as ET
from figure_system.common import ROOT,read
from figure_system.qa import inspect_exports as original
from .oracle import inspect as coordinate_oracle,point,NS
p=ROOT/'vendor/nature_qa/scripts/audit_figure_collisions.py'
loader=importlib.util.spec_from_file_location('_closure_nature',p);nature=importlib.util.module_from_spec(loader);sys.modules[loader.name]=nature;loader.loader.exec_module(nature)
def classify(pdf,raw):
 geometries=nature.extract_pdf_geometry(Path(pdf));result=[]
 for finding in raw.get('findings',[]):
  row={'finding':finding,'classification':'UNRESOLVED','evidence':{}}
  g=geometries[finding['page']-1];bb=finding['text_bbox'];text=''.join(finding.get('text','').split())
  # Narrow exception: a duplicated/degenerate dictionary fragment of an actual
  # x-tick draw, outside the real glyphs, touches only geometry above the x-axis.
  # Native axis-title overscores and arbitrary fragments are never exempted.
  axis=[s for s in g.strokes if s.bbox[2]-s.bbox[0]>.65*(g.bbox[2]-g.bbox[0])
   and s.bbox[3]-s.bbox[1]<.01]
  if finding['kind']=='text-stroke' and axis and text:
   baseline=max(s.bbox[1] for s in axis)
   traces=[t for t in g.traces if text in ''.join(t.text.split()) and t.bbox[1]>baseline+2
    and t.bbox[0]-.1<=bb[0]<=t.bbox[2]+.1 and bb[3]>=t.bbox[1] and bb[1]<=t.bbox[3]]
   # Exclude any separately drawn trace with this fragment's own text/bbox.
   duplicate=bool(traces) and not any(t.text.strip()==finding['text'] and abs(t.bbox[1]-bb[1])<.1 for t in g.traces)
   hits=[s for s in g.strokes if s.index in finding.get('object_indexes',[])]
   safe=hits and all(s.bbox[3]<=baseline+.05 for s in hits)
   if duplicate and safe:
    row['classification']='PDF_FRAGMENT_ARTIFACT'
    row['evidence']={'actual_draws':[{'text':t.text,'bbox':t.bbox,'trace_index':t.index} for t in traces],
     'dictionary_fragment_bbox':bb,'native_axis_baseline_pt':baseline,'all_hit_strokes_stop_at_axis':True,
     'glyphs_below_axis_by_pt':min(t.bbox[1]-baseline for t in traces),'separate_fragment_draw_absent':True}
   else:
    # A real glyph-crossing is a collision; unproven font anomalies stay unresolved.
    if any(nature.rect_intersection(t.bbox,finding['other_bbox']) for t in g.traces if text and text in ''.join(t.text.split())):
     row['classification']='TRUE_COLLISION'
  result.append(row)
 return {'pass':all(r['classification']=='PDF_FRAGMENT_ARTIFACT' for r in result),'findings':result,
  'unchanged_thresholds':raw.get('thresholds'),'scope':'Only proven x-tick dictionary duplication; native overscores and unresolved findings remain blockers'}
def exports(pdf,svg,spec):
 q=original(pdf,svg,spec)
 raw=q['nature']['audit_figure_collisions.py']['result'];c=classify(pdf,raw);q['fragment_classification']=c
 if c['pass'] and 'nature_collision_audit' in q['failures']:
  q['failures'].remove('nature_collision_audit');q['checks']['nature_collision_audit']['raw_pass']=False
  q['checks']['nature_collision_audit']['pass']=True;q['checks']['nature_collision_audit']['detail']='All raw findings proven duplicate x-tick fragments; original report retained'
 if spec.get('time_axis_mode'):
  co=coordinate_oracle(Path(pdf).parent if (Path(pdf).parent/'figure_spec.json').exists() else Path(pdf).parent.parent,Path(pdf).parent)
  q['coordinate_oracle']=co
  if not co['pass']:q['failures'].append('actual_rendered_x_coordinate')
 q['status']='AUTOMATED PASS' if not q['failures'] else 'FAILED'
 return q
def bar_geometry(bundle):
 bundle=Path(bundle);spec=read(bundle/'figure_spec.json');checks={};details={}
 for stage,folder in [('fresh',bundle),('reopen',bundle/'independent_reopen')]:
  report=read(folder/('origin_render_report.json' if stage=='fresh' else 'reopen_report.json'))['readback']
  root=ET.parse(next(folder.glob('*.svg'))).getroot();vb=list(map(float,re.split(r'[, ]+',root.attrib['viewBox'])))
  xaxis=next(e for e in root.iter() if e.attrib.get(NS+'scope')=='Layer0.Axis0.SubAxis0.Line')
  yaxis=next(e for e in root.iter() if e.attrib.get(NS+'scope')=='Layer0.Axis1.SubAxis0.Line')
  xa=np.array(list(map(float,re.findall(r'-?[0-9.]+',xaxis.attrib['points'])))).reshape(-1,2)
  ya=np.array(list(map(float,re.findall(r'-?[0-9.]+',yaxis.attrib['points'])))).reshape(-1,2)
  approved=__import__('pandas').read_csv(bundle/'plot_data.csv',float_precision='round_trip')
  with Image.open(next(folder.glob('*.png'))) as im:rgb=np.asarray(im.convert('RGB'));sx=rgb.shape[1]/vb[2];sy=rgb.shape[0]/vb[3]
  for gid,g in spec['groups'].items():
   native=[p for p in report['plots'] if p['pid']==203 and p['binding'] and p['binding']['group_id']==gid]
   rects=[e for e in root.iter() if e.tag.endswith('rect') and e.attrib.get('fill')==g['fill'] and float(e.attrib.get('height',0))>50]
   check=len(native)==1 and len(rects)==1
   for e in rects:
    a=e.attrib;w=float(a['width']);h=float(a['height']);x=float(a['x']);y=float(a['y'])
    source=next(v for v in spec['series'] if v['group_id']==gid and v['role']=='group_summary')
    row=approved.loc[approved[source['y']].notna()].iloc[0]
    ex=xa[0,0]+(row[source['x']]-spec['x_limits'][0])/(spec['x_limits'][1]-spec['x_limits'][0])*(xa[1,0]-xa[0,0])
    ey=ya[0,1]+(row[source['y']]-spec['y_limits'][0])/(spec['y_limits'][1]-spec['y_limits'][0])*(ya[1,1]-ya[0,1])
    check=check and abs(x+w/2-ex)<=2.01 and abs(y-ey)<=2.01
    check=check and w>5 and h>50 and 0<float(a.get('fill-opacity',1))<=.35
    crop=rgb[round((y+h*.5)*sy):round((y+h*.7)*sy),round((x+w*.3)*sx):round((x+w*.7)*sx)]
    color=np.array([int(g['fill'][i:i+2],16) for i in (1,3,5)])
    blended=np.rint(color*.3+255*.7)
    check=check and crop.size>0 and np.any(np.max(np.abs(crop.astype(float)-blended),axis=2)<8)
   checks[stage+'_native_vector_rendered_bar_'+gid]=bool(check)
   raw=[p for p in report['plots'] if p['pid'] in (201,202) and p['binding'] and p['binding']['group_id']==gid and p['binding']['role']=='unit']
   raw_e=[e for e in root.iter() if NS+'data' in e.attrib and point(e) is not None and e.attrib.get('fill')==g['fill']]
   visible=[]
   for e in raw_e:
    x,y=point(e);cx,cy=round(x*sx),round(y*sy);crop=rgb[max(0,cy-5):cy+6,max(0,cx-5):cx+6]
    color=np.array([int(g['fill'][i:i+2],16) for i in (1,3,5)])
    visible.append(crop.size>0 and np.any(np.max(np.abs(crop.astype(float)-color),axis=2)<12))
   checks[stage+'_raw_primary_points_visible_'+gid]=bool(raw and len(raw_e)==4 and all(visible) and all(p['properties']['transparency']>=65 for p in native))
   details[stage+'_'+gid]={'native_bars':len(native),'svg_bars':len(rects),'svg_raw_points':len(raw_e),'png_raw_visible':list(map(bool,visible))}
 return {'pass':all(checks.values()),'checks':checks,'evidence':details,'does_not_infer_absence_from_transparent_pdf_forms':True}

