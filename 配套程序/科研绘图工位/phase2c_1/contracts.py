"""Additive time-axis and secondary-display gates; existing semantic gate stays intact."""
from pathlib import Path
import numpy as np,pandas as pd
from figure_system.common import read
from phase2c.semantics import validate,validate_render_plan,validate_style_owner,SemanticsError
def need(value,message):
 if not value:raise SemanticsError(message)
def validate_target(base):
 base=Path(base);c=read(base/'PLOT_SEMANTICS_CONTRACT.json');s=read(base/'figure_spec.json');a=read(base/'analysis_manifest.json')
 validate(c,base);validate_render_plan(c,s,base);validate_style_owner(c,s)
 data=pd.read_csv(base/'plot_data.csv',float_precision='round_trip');obs=pd.read_csv(base/'observations.csv',float_precision='round_trip')
 if s.get('native_display_labels'):
  need(s['native_display_labels']==a.get('approved_display_labels')==c.get('approved_display_labels'),'Display labels differ from the approved ID mapping')
  need(set(s['native_display_labels'])==set(v['y'] for v in s['series']),'Display label mapping must preserve each sample identity')
 t=c.get('time_axis')
 if t:
  mode=t['mode'];need(mode in ('LINEAR_NUMERIC','LOG_NUMERIC','CATEGORICAL_SCHEDULE'),'Unknown time-axis mode')
  need(s.get('time_axis_mode')==mode,'Native axis mode differs from approved time contract')
  schedule=np.array(t['schedule_h'],dtype=float)
  for series in s['series']:
   x=data[series['x']].dropna().to_numpy()
   if mode=='CATEGORICAL_SCHEDULE':
    need(c['x_variable']['type']=='ordinal' and c.get('ordinal_connection_reason'),'Categorical schedule needs an explicit ordering purpose')
    need(np.array_equal(x,np.arange(1,len(schedule)+1)),'Categorical schedule coordinates must be approved category indices')
    need(read(base/'PLOT_DECISION_RECORD.json').get('x_spacing_does_not_encode_elapsed_time') is True,'Categorical spacing disclosure missing')
   else:
    need(c['x_variable']['type']=='continuous' and np.array_equal(x,schedule),'Numerical time coordinates changed')
    need((s['x_scale']=='log10')==(mode=='LOG_NUMERIC'),'Fake log or unexpected nonlinear time')
    if mode=='LOG_NUMERIC':
     need((schedule>0).all() and (pd.to_numeric(obs['x'])>0).all(),'t0/nonpositive time is not approved for native log')
     need(t.get('zero_policy'),'Contract-owned zero handling is missing')
  if c['design']['independent_by_x']:need(not any(v.get('individual_trace') for v in s['series']),'Independent time cohorts cannot form trajectories')
 if c.get('nested_display'):
  d=c['nested_display'];need(a.get('approved_nested_display')==d,'Secondary display was not approved')
  need(c['point_semantics']['subsample_display'] and c['point_semantics']['primary_level']=='experimental_unit','Primary inference must remain unit-level')
  parent=dict(zip(obs['field_id'],obs['unit_id']))
  for series in s['series']:
   if series['role']=='subsamples':
    ids=series.get('subsample_id_mapping',[])
    need(len(ids)==len(data[series['y']].dropna()),'Subsample identity lost')
    need(all(parent.get(v['field_id'])==v['animal_id'] for v in ids),'Field connected to the wrong independent animal')
  need(d['secondary_marker_pt']<d['primary_marker_pt'] and d['secondary_transparency_percent']>=65,'Subsamples obscure independent unit points')
 return True

