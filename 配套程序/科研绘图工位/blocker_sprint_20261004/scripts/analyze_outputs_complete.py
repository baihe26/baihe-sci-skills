"""Read-only vector and raster comparisons; established parsers supply all geometry."""
from pathlib import Path
import sys,json,hashlib,collections
import numpy as np
import pymupdf
from PIL import Image,ImageChops
from defusedxml import ElementTree as ET
S=Path(__file__).resolve().parents[1];R=S.parent;sys.path.insert(0,str(R/'src'))
from figure_system.common import read,write_new,sha
from figure_system.qa import inspect_exports

def objects(path):
 with pymupdf.open(path) as original:
  if original.is_pdf:doc=original
  else:doc=pymupdf.open('pdf',original.convert_to_pdf())
  page=doc[0]
  lines=[{'text':''.join(s['text'] for s in l['spans']),'bbox_pt':list(l['bbox']),'direction':list(l['dir']),'spans':l['spans']} for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines']]
  vectors=[{'type':d['type'],'bbox_pt':list(d['rect']),'width_pt':d['width'],'color':d['color'],'fill':d['fill'],'items':[[str(v) for v in i] for i in d['items']]} for d in page.get_drawings()]
  result={'parser':'PyMuPDF '+pymupdf.VersionBind,'input_format':path.suffix,'svg_bbox_note':'MuPDF SVG->PDF interpretation; not browser getBBox; font substitution possible' if path.suffix=='.svg' else None,'page_pt':list(page.rect),'text_lines':lines,'vectors':vectors}
  if doc is not original:doc.close()
  return result

def inspect(folder,spec=None):
 result={}
 for ext in ['pdf','svg']:
  f=next(folder.glob('*.'+ext));result[ext]=objects(f)
 f=next(folder.glob('*.svg'));root=ET.parse(f).getroot();result['svg_xml']={'root':root.attrib,'tag_counts':dict(collections.Counter(e.tag.split('}')[-1] for e in root.iter())),'texts':[{'text':''.join(e.itertext()),'attributes':e.attrib} for e in root.iter() if e.tag.endswith('}text')],'line_objects':[e.attrib for e in root.iter() if e.tag.endswith('}line')]}
 result['file_hashes']={f.name:sha(f) for f in folder.iterdir() if f.suffix in ['.png','.pdf','.svg','.opju']}
 if spec:
  if not (folder/'QA_REPORT.json').exists():write_new(folder/'QA_REPORT.json',inspect_exports(next(folder.glob('*.pdf')),next(folder.glob('*.svg')),spec))
  result['qa_summary']=read(folder/'QA_REPORT.json')['nature']['audit_figure_collisions.py']['result'].get('summary')
 return result

def compare(a,b,name):
 x=Image.open(next(a.glob('*.png'))).convert('RGB');y=Image.open(next(b.glob('*.png'))).convert('RGB')
 result={'a':str(a),'b':str(b),'png_same_shape':x.size==y.size}
 if x.size==y.size:
  delta=ImageChops.difference(x,y);arr=np.asarray(delta);result.update(png_changed_pixels=int(np.any(arr!=0,axis=2).sum()),png_diff_bbox=delta.getbbox())
  Image.blend(x,y,0.5).save(S/'evidence'/f'{name}_overlay.png');delta.save(S/'evidence'/f'{name}_difference.png')
 for ext in ['pdf','svg']:
  aa=objects(next(a.glob('*.'+ext)));bb=objects(next(b.glob('*.'+ext)))
  result[ext]={'text_lines_exact_equal':aa['text_lines']==bb['text_lines'],'vectors_exact_equal':aa['vectors']==bb['vectors'],'page_equal':aa['page_pt']==bb['page_pt'],'a_titles':[l for l in aa['text_lines'] if any(t in l['text'] for t in ['Condition','Time (day)','Response (a.u.)'])],'b_titles':[l for l in bb['text_lines'] if any(t in l['text'] for t in ['Condition','Time (day)','Response (a.u.)'])]}
 return result

if __name__=='__main__':
 results={}
 for p in sorted((S/'artifacts').iterdir()):
  if not list(p.glob('*.svg')) or not list(p.glob('*.pdf')):continue
  if (p/'figure_spec.json').exists():spec=read(p/'figure_spec.json')
  elif (p/'request.json').exists() and 'parent' in read(p/'request.json'):spec=read(Path(read(p/'request.json')['parent'])/'figure_spec.json')
  else:spec=None
  results[p.name]=inspect(p,spec)
  print(p.name,results[p.name].get('qa_summary'),flush=True)
 comparisons={}
 for fig in ['FigA','FigB']:
  p=R/'artifacts/native_edit_tests_r2_recheck'/fig;comparisons['old_manual_'+fig]=compare(p,p/'independent_reopen','old_manual_'+fig)
  for prefix in ['B_English','D_Chinese_restored']:
   b=S/'artifacts'/f'{prefix}_{fig}';a=S/'artifacts'/f'A_Chinese_{fig}'
   if b.exists() and list(b.glob('*.png')):comparisons[f'A_vs_{prefix}_{fig}']=compare(a,b,f'A_vs_{prefix}_{fig}')
  b=S/'artifacts'/f'B_English_{fig}';c=S/'artifacts'/f'C_English_reopen_{fig}'
  if list(c.glob('*.png')):comparisons['B_C_'+fig]=compare(b,c,'B_C_'+fig)
 for mode in ['current','native_default','page_ytitle']:
  for fig in ['FigA','FigB']:
   base=f'geometry_{mode}_{fig}';a=S/'artifacts'/(base+'_repeat1');b=S/'artifacts'/(base+'_repeat2')
   if list(a.glob('*.png')) and list(b.glob('*.png')):comparisons[base+'_repeat']=compare(a,b,base+'_repeat')
   for repeat in [1,2]:
    a=S/'artifacts'/f'{base}_repeat{repeat}';b=S/'artifacts'/f'{base}_repeat{repeat}_reopen'
    if list(a.glob('*.png')) and list(b.glob('*.png')):comparisons[f'{base}_{repeat}_reopen']=compare(a,b,f'{base}_{repeat}_reopen')
 write_new(S/'evidence/export_object_analysis_complete.json',results);write_new(S/'evidence/visual_comparisons_complete.json',comparisons)

