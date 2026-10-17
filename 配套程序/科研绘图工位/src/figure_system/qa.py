"""File-format inspection reuses Nature, PyMuPDF and defusedxml; assertions are fixture-specific."""
import sys,re,subprocess,json,math,csv
from collections import Counter
from pathlib import Path
import pymupdf
from defusedxml import ElementTree as ET
from .common import ROOT,NATURE,EDITAPLOT,sha,read,require_hash
sys.path.insert(0,str(EDITAPLOT/"runtime/src"))
from origin_sciplot.origin_backend.base_style_contract import pt_to_origin_width_units

def inspect_exports(pdf,svg,spec):
 failures=[];checks={};t=spec['tokens']
 def check(name,ok,detail=None):
  checks[name]={'pass':bool(ok),'detail':detail}
  if not ok:failures.append(name)
 if not Path(pdf).read_bytes().startswith(b'%PDF-'):raise ValueError('not a PDF')
 with pymupdf.open(pdf) as doc:
  check('pdf_single_page',len(doc)==1);page=doc[0];mm=[page.rect.width*25.4/72,page.rect.height*25.4/72]
  # Native expGraph rounds its bounding box to an integer pt: <1pt outward rounding.
  check('pdf_actual_dimensions',all(abs(a-b)<=0.36 for a,b in zip(mm,[t['width_mm'],t['height_mm']])),mm)
  spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'] if s['text'].strip()]
  check('pdf_effective_text_floor',bool(spans) and min(s['size'] for s in spans)>=5,min((s['size'] for s in spans),default=None))
  check('pdf_no_raster',not page.get_images(full=True),len(page.get_images(full=True)))
  check('pdf_text_bounds',all(page.rect+(-0.6,-0.6,0.6,0.6) & pymupdf.Rect(s['bbox']) == pymupdf.Rect(s['bbox']) for s in spans))
  check('pdf_no_control_glyphs',all(all(ord(c)>=32 for c in s['text']) for s in spans))
 root=ET.parse(svg).getroot();tags=[e.tag.split('}')[-1] for e in root.iter()]
 def length(value):
  m=re.fullmatch(r'([0-9.]+)(in|mm|pt)',value)
  if not m:raise ValueError('unsupported SVG unit')
  return float(m[1])*{'in':25.4,'mm':1,'pt':25.4/72}[m[2]]
 smm=[length(root.attrib[k]) for k in ['width','height']]
 check('svg_actual_dimensions',all(abs(a-b)<=0.08 for a,b in zip(smm,[t['width_mm'],t['height_mm']])),smm)
 check('svg_editable_text','text' in tags);check('svg_no_decoration',not(set(tags)&{'linearGradient','radialGradient','filter','feDropShadow','script','foreignObject'}));check('svg_no_raster','image' not in tags)
 vb=list(map(float,re.split(r'[, ]+',root.attrib['viewBox'].strip())))
 sizes=[float(e.attrib['font-size'])*smm[0]*72/25.4/vb[2] for e in root.iter() if 'font-size' in e.attrib]
 if not sizes:
  # matplotlib writes CSS-style font declarations, Nature/PyMuPDF remain final-size source.
  check('svg_font_floor_from_pdf',checks['pdf_effective_text_floor']['pass'])
 else:check('svg_effective_font_floor',min(sizes)>=5,min(sizes))
 text=Path(svg).read_text(encoding='utf-8').lower()
 check('svg_group_colors',all(g['edge'].lower() in text and g['fill'].lower() in text for g in spec['groups'].values()))
 nature={}
 for script in ['audit_pdf_text.py','audit_figure_collisions.py']:
  run=subprocess.run([sys.executable,str(NATURE/'scripts'/script),str(pdf),'--json'],capture_output=True,text=True,encoding='utf-8')
  try:result=json.loads(run.stdout)
  except ValueError:result={'stdout':run.stdout,'stderr':run.stderr}
  nature[script]={'returncode':run.returncode,'result':result}
 check('nature_collision_audit',nature['audit_figure_collisions.py']['returncode']==0,nature['audit_figure_collisions.py']['result'].get('verdict'))
 return {'status':'AUTOMATED PASS' if not failures else 'FAILED','failures':failures,'checks':checks,'actual_mm':{'pdf':mm,'svg':smm},'nature':nature,'nature_tf_limitation':'Raw Tf is preserved separately; effective PyMuPDF span sizes and SVG glyph sizes control final-size checks (upstream issue 238).','human_accepted':False,'visual_review':'PENDING'}

def check_native(spec,report):
 r=report['readback'];t=spec['tokens'];fail=[]
 def ck(name,ok):
  if not ok:fail.append(name)
 ck('native_page_size',all(abs(r['actual_page_mm'][k]-t[n])<0.05 for k,n in [('width','width_mm'),('height','height_mm')]))
 roles=['mean','sample_sd']+(['raw'] if spec['raw_required'] else [])
 expected=Counter((gid,role) for gid in spec['groups'] for role in roles)
 observed=Counter((p['group_id'],p['role']) for p in r['plots'])
 ck('complete_native_object_set',observed==expected and r['native_plot_count']==sum(expected.values()) and sorted(p['index'] for p in r['plots'])==list(range(1,sum(expected.values())+1)))
 rows=list(csv.DictReader(Path(spec['summary_path']).open(encoding='utf-8-sig',newline='')))
 for p in r['plots']:
  if p['group_id'] not in spec['groups'] or p['role'] not in roles:
   ck('unexpected_native_object',False);continue
  g=spec['groups'][p['group_id']];role=p['role'];pid=231 if role=='sample_sd' else 201 if role=='raw' or spec['raw_required'] else 202
  ck('native_type_'+str(p['index']),p['native']['pid']==pid)
  ck('binding_'+str(p['index']),p['binding']['native_dataset']['equal'])
  ck('count_'+str(p['index']),len(p['y_values'])==p['expected_count'])
  ck('color_'+str(p['index']),p['get']['color']==p['expected_color'])
  width=t['error_width_pt'] if role=='sample_sd' else t['line_width_pt']
  size=t['error_cap_pt'] if role=='sample_sd' else t['raw_marker_size_pt'] if role=='raw' else t['marker_size_pt']
  alpha=t['raw_alpha'] if role=='raw' else 1
  ck('stroke_size_alpha_'+str(p['index']),abs(p['get']['width_units']-pt_to_origin_width_units(width))<1e-8 and abs(p['get']['size_pt']-size)<1e-8 and abs(p['native']['transparency']-100*(1-alpha*g['alpha']))<1e-8)
  if role=='mean' and not spec['raw_required']:ck('line_style_'+str(p['index']),p['get']['line_style']=={'solid':0,'dash':1,'dot':2}[g['line_style']])
  if role!='raw':
   expected=[float(v['std' if role=='sample_sd' else 'mean']) for v in rows if v['group']==g['display_name']]
   ck('approved_values_'+str(p['index']),len(expected)==len(p['y_values']) and all(abs(a-b)<1e-12 for a,b in zip(expected,p['y_values'])))
  if role!='sample_sd':
   ck('symbol_'+str(p['index']),p['get']['symbol']=={'circle':2,'square':1,'triangle':3}[g['marker']])
   ck('solid_symbol_'+str(p['index']),p['get']['interior']==0)
   ck('fill_'+str(p['index']),p['get']['fill_color']==p['expected_fill'])
 if spec['raw_required']:ck('raw_presence',sum(p['expected_count'] for p in r['plots'] if p['role']=='raw')==16*len(spec['groups']))
 ck('source_roundtrip',len(report['source_worksheets'])==len(spec['groups']) and all(s['all_original_columns_equal'] for s in report['source_worksheets']))
 for axis in ['x','y']:
  vals=r['axes'][axis];ck('axis_'+axis,vals['label.pt']==t['tick_pt'] and vals['thickness']==t['axis_width_pt'] and vals['tickthickness']==t['tick_width_pt'] and vals['ticks']==2 and vals['ticklength']==t['tick_length_pt'] and vals['showAxes']==(3 if t['frame']=='box' else 1) and vals['showGrids']==0)
 ck('legend',r['legend']['size_pt']==t['legend_pt'] and r['legend']['frame']==0)
 return {'status':'NATIVE PASS' if not fail else 'FAILED','failures':fail}
