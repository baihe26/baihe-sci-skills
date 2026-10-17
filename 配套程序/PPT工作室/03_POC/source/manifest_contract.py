"""Small manifest contract: reject ambiguity before any Office mutation."""
import hashlib,json,math
from pathlib import Path
TYPES={'text','shape','picture','chart','table','connector','group'}
def validate(m):
 if m.get('schema_version')!='0.1':raise ValueError('unsupported schema')
 w,h=m['deck']['canvas'];slide_ids=set()
 if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0 for v in (w,h)):raise ValueError('invalid canvas')
 for s in m['slides']:
  if s['id'] in slide_ids:raise ValueError('duplicate slide id')
  slide_ids.add(s['id']);seen=set()
  for o in s['objects']:
   if not o.get('id') or o['id'] in seen:raise ValueError('duplicate or missing semantic id')
   if o['type'] not in TYPES:raise ValueError('unsupported object type')
   if o['type']=='connector' and (o['begin'] not in seen or o['end'] not in seen):raise ValueError('relationship endpoint must exist first')
   if o['type']=='group' and (len(o['members'])<2 or len(set(o['members']))!=len(o['members']) or any(x not in seen for x in o['members'])):raise ValueError('invalid group members')
   if 'bbox' in o:
    x,y,bw,bh=o['bbox']
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in o['bbox']) or min(x,y)<0 or min(bw,bh)<=0 or x+bw>w+.01 or y+bh>h+.01:raise ValueError(('offslide or invalid bbox',o['id']))
   if o['type']=='chart':
    if not o['categories'] or len(o['categories'])!=len(o['values']) or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in o['values']):raise ValueError('invalid chart data')
   if o['type']=='table':
    d=o['data']
    if not d or not d[0] or any(len(r)!=len(d[0]) for r in d):raise ValueError('ragged table')
   if o['type']=='picture' and not Path(o['path']).is_file():raise ValueError('missing asset')
   seen.add(o['id'])
 return True

def digest(m):return hashlib.sha256(json.dumps(m,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def within(path,root):
 p,r=Path(path).resolve(),Path(root).resolve()
 if not p.is_relative_to(r):raise ValueError('output outside project')
 return p
