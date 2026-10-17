"""Small manuscript state resolver. Generic validation belongs to jsonschema."""
import copy,re
from pathlib import Path
from jsonschema import Draft202012Validator
from .common import ROOT,read,sha,write_new,require_hash

def validate_state(state):
 Draft202012Validator(read(ROOT/'fixtures/figurestate.schema.json')).validate(state)
 if state['parent'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',state['parent']['version']):raise ValueError('invalid parent version')
 if state['group_registry_version']!=state['style_version']:raise ValueError('registry version mismatch')
 orders=[]
 for key,g in state['groups'].items():
  if g['alpha']!=1:raise ValueError('group alpha other than 1 is not verified by this MVP')
  if key!=g['stable_group_id']:raise ValueError('group ID mismatch')
  orders.append(g['display_order'])
 if len(set(orders))!=len(orders):raise ValueError('duplicate group order')
 t=state['tokens']
 for k in ['width_mm','height_mm','axis_title_pt','tick_pt','legend_pt','marker_size_pt','error_width_pt']:
  if t[k]<=0:raise ValueError(f'nonpositive {k}')
 if t['background']!='#FFFFFF' or t['fill_alpha']!=1 or t['line_alpha']!=1:raise ValueError('unsupported MVP fill/line/background semantics')
 if t['font_family']!='Arial' or t['grid'] or t['legend_frame']:raise ValueError('unsupported MVP style')
 if t['tick_direction']!='out' or t['frame'] not in ['box','left_bottom']:raise ValueError('unsupported axis grammar')
 for key in ['fill_alpha','line_alpha','band_alpha','raw_alpha']:
  if not 0<=t[key]<=1:raise ValueError('alpha out of range')
 for e in state['feedback']:
  if e['scope']['kind']=='group' and e['scope']['id'] not in state['groups']:raise ValueError('unknown feedback group')
 return state

def load_state(version):
 if not re.fullmatch(r'[A-Za-z0-9_.-]+',version):raise ValueError('invalid version')
 path=ROOT/'fixtures/styles'/f'{version}.json';s=validate_state(read(path))
 if s['style_version']!=version:raise ValueError('style filename/version mismatch')
 if s['parent']:
  parent=ROOT/'fixtures/styles'/f"{s['parent']['version']}.json"
  require_hash(parent,s['parent']['sha256'])
 return s

def resolve(figure_id,version,groups=None):
 if figure_id not in ['FigA','FigB']:raise ValueError('unsupported figure')
 import sys
 sys.path.insert(0,str(ROOT))
 from phase2c.legacy import gate
 gate(figure_id)
 s=load_state(version); c=read(ROOT/'fixtures/contracts'/f'{figure_id}.json')
 if c['manuscript_id']!=s['manuscript_id'] or figure_id not in s['figures']:raise ValueError('manuscript mismatch')
 a=read(ROOT/'fixtures/analysis_manifest.json')
 require_hash(ROOT/'fixtures/analysis_manifest.json',c['analysis_sha256'])
 for name,key in [('source','source_sha256'),('summary','summary_sha256')]:
  require_hash(ROOT/'fixtures/source'/c[name],c[key])
 if c['center']!='mean' or c['error']!='sample_sd' or c['n_per_cell']!=8:raise ValueError('unapproved statistics')
 chosen=list(c['groups'] if groups is None else groups)
 if not chosen or len(set(chosen))!=len(chosen) or any(g not in c['groups'] for g in chosen):raise ValueError('invalid subset')
 ordered=sorted(chosen,key=lambda g:s['groups'][g]['display_order'])
 return {**c,'groups':{g:copy.deepcopy(s['groups'][g]) for g in ordered},'all_groups':copy.deepcopy(s['groups']),'style_version':version,'style_sha256':sha(ROOT/'fixtures/styles'/f'{version}.json'),'group_registry_version':s['group_registry_version'],'tokens':copy.deepcopy(s['tokens']),'subset':ordered!=c['groups'],'subset_reason':'USER_AUTHORIZED_PALETTE_REGRESSION' if ordered!=c['groups'] else None,'source_path':str(ROOT/'fixtures/source'/c['source']),'summary_path':str(ROOT/'fixtures/source'/c['summary']),'analysis_path':str(ROOT/'fixtures/analysis_manifest.json'),'backend':'EditaPlot-Origin','renderer_statistics':'NONE; approved CSV only','template':'Origin built-in Line; per-project explicit style','theme':None,'capabilities_not_applicable':['band_alpha (native error bars used)']}

def publish_style(state):
 from filelock import FileLock
 validate_state(state)
 if not state['parent']:raise ValueError('new version requires parent')
 parent=load_state(state['parent']['version'])
 require_hash(ROOT/'fixtures/styles'/f"{parent['style_version']}.json",state['parent']['sha256'])
 if state['manuscript_id']!=parent['manuscript_id']:raise ValueError('cannot change manuscript identity')
 with FileLock(str(ROOT/'fixtures/styles/.writer.lock')):
  write_new(ROOT/'fixtures/styles'/f"{state['style_version']}.json",state)
