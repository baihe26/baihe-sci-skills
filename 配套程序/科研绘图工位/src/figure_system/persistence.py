"""Exact rendered comparison using the project's existing read-only geometry helper.

Internal axis-title rectangles remain diagnostics, not a substitute for output.
No new parser, raster tolerance or figure layout is introduced.
"""
import importlib.util
from PIL import Image,ImageChops
from .common import ROOT

_spec=importlib.util.spec_from_file_location('_phase2_existing_visual',ROOT/'blocker_sprint_20261004/scripts/analyze_outputs_complete.py')
_existing=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_existing)

def compare_rendered(a,b):
 a=__import__('pathlib').Path(a);b=__import__('pathlib').Path(b)
 with Image.open(next(a.glob('*.png'))) as aa,Image.open(next(b.glob('*.png'))) as bb:
  same=aa.size==bb.size
  pixels=None if not same else sum(px!=(0,0,0) for px in ImageChops.difference(aa.convert('RGB'),bb.convert('RGB')).getdata())
 report={'png_same_shape':same,'png_changed_pixels':pixels,'formats':{},'method':'Existing project PyMuPDF text/vector geometry + exact whole PNG pixels; zero tolerance'}
 for ext in ['pdf','svg']:
  x=_existing.objects(next(a.glob('*.'+ext)));y=_existing.objects(next(b.glob('*.'+ext)))
  report['formats'][ext]={k:x[k]==y[k] for k in ['page_pt','text_lines','vectors']}
 report['pass']=same and pixels==0 and all(all(v.values()) for v in report['formats'].values())
 return report

def compare_native_and_rendered(saved,opened,a,b):
 fields=[k for k in saved if k!='title_geometry' and saved[k]!=opened[k]]
 geometry_semantics={k:v for k,v in saved['title_geometry'].items() if k.endswith('.attach') or k.startswith('page.')}
 opened_semantics={k:v for k,v in opened['title_geometry'].items() if k.endswith('.attach') or k.startswith('page.')}
 rendered=compare_rendered(a,b)
 return {'pass':not fields and geometry_semantics==opened_semantics and rendered['pass'],'core_native_equal':not fields,'changed_core_fields':fields,'page_and_title_attachment_equal':geometry_semantics==opened_semantics,'raw_internal_geometry_equal':saved['title_geometry']==opened['title_geometry'],'saved_internal_geometry':saved['title_geometry'],'reopened_internal_geometry':opened['title_geometry'],'rendered':rendered}
