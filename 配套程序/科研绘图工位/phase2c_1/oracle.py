"""Origin SVG coordinates compared with approved numerical transforms.
Uses defusedxml and Origin metadata. Integer quantization permits 1 SVG unit.
"""
import re
from pathlib import Path
import numpy as np,pandas as pd
from defusedxml import ElementTree as ET
from figure_system.common import read
NS='{http://www.originlab.com/namespaces/olab}'
def point(e):
 tag=e.tag.split('}')[-1];a=e.attrib
 if tag=='circle':return float(a['cx']),float(a['cy'])
 if tag=='rect':return float(a['x'])+float(a['width'])/2,float(a['y'])+float(a['height'])/2
 if tag=='polygon':
  xy=np.array(list(map(float,re.findall(r'-?[0-9.]+',a['points'])))).reshape(-1,2)
  return tuple((xy.min(axis=0)+xy.max(axis=0))/2)
 return None
def inspect(bundle,folder=None):
 bundle=Path(bundle);folder=Path(folder or bundle);s=read(bundle/'figure_spec.json')
 f=pd.read_csv(bundle/'plot_data.csv',float_precision='round_trip')
 root=ET.parse(next(folder.glob('*.svg'))).getroot()
 axis=next(e for e in root.iter() if e.attrib.get(NS+'scope')=='Layer0.Axis0.SubAxis0.Line')
 xy=np.array(list(map(float,re.findall(r'-?[0-9.]+',axis.attrib['points'])))).reshape(-1,2)
 left,width=float(xy[0,0]),float(xy[1,0]-xy[0,0])
 groups={}
 for e in root.iter():
  if NS+'data' not in e.attrib or point(e) is None:continue
  raw=e.attrib[NS+'data'];mx=re.search(r'"X"\s*:\s*"([^"]+)"',raw);my=re.search(r'"Y"\s*:\s*"([^"]+)"',raw)
  if not mx or not my:continue
  key=e.attrib[NS+'scope'];groups.setdefault(key,[]).append((float(mx[1]),float(my[1]),point(e)[0]))
 checks=[]
 for series in s['series']:
  if series['plot_type'] not in ('s','y') or not series.get('x'):continue
  expected=f[[series['x'],series['y']]].dropna().to_numpy()
  candidates=[]
  for scope,pts in groups.items():
   if len(pts)==len(expected) and np.allclose(np.array(pts)[:,1],expected[:,1],atol=1e-10,rtol=0):candidates.append((scope,pts))
  if len(candidates)!=1:
   checks.append({'series':series['y'],'pass':False,'reason':'SVG markers not uniquely matched to approved Y','candidate_count':len(candidates)});continue
  scope,pts=candidates[0];actual=np.array(pts);lo,hi=s['x_limits'][:2]
  transform=np.log10 if s['x_scale']=='log10' else lambda v:v
  ex=(transform(expected[:,0])-transform(lo))/(transform(hi)-transform(lo));ac=(actual[:,2]-left)/width
  delta=(ac-ex)*width
  ok=np.allclose(actual[:,0],expected[:,0],atol=1e-10,rtol=0) and max(abs(delta))<=2.01
  checks.append({'series':series['y'],'scope':scope,'pass':bool(ok),'approved_x':expected[:,0].tolist(),'native_svg_x':actual[:,0].tolist(),
   'expected_normalized_x':ex.tolist(),'rendered_normalized_x':ac.tolist(),'error_svg_units':delta.tolist()})
 return {'pass':bool(checks) and all(c['pass'] for c in checks),'axis_mode':s.get('time_axis_mode',s['x_scale']),
  'plot_rect_svg':{'left':left,'width':width},'tolerance_svg_units':2.01,'reason':'Two integer quantizations: plot symbol placement and axis/background SVG endpoints; same across controls','checks':checks}

