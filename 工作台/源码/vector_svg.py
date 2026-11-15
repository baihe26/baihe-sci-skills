"""Lightweight SVG primitives; no PDF, native app or frozen-engine import.

The basic arrow geometry follows the bundled original scientific-design replay.
Its scientific contracts remain checked by scientific_gate, not by this renderer.
"""
import html
import math
from core import GateError


def ellipse_rect(data):
    if all(k in data for k in ('cx','cy','rx','ry')):
        return data['cx']-data['rx'],data['cy']-data['ry'],data['rx']*2,data['ry']*2
    return data['x'],data['y'],data['width'],data['height']


def arrow_paths(points,encoding):
    end=points[-1];tail=next((p for p in reversed(points[:-1]) if p!=end),None)
    if tail is None:raise GateError('COINCIDENT_RELATION_ENDPOINTS')
    dx,dy=end[0]-tail[0],end[1]-tail[1];length=math.hypot(dx,dy);ux,uy=dx/length,dy/length
    if encoding=='inhibition_bar':return [[end[0]-uy*9,end[1]+ux*9],[end[0]+uy*9,end[1]-ux*9]]
    if encoding in ('solid_arrow','dashed_arrow'):
        return [[end[0]-ux*11-uy*5,end[1]-uy*11+ux*5],end,[end[0]-ux*11+uy*5,end[1]-uy*11-ux*5]]
    return []


def element_svg(element):
    d=element['data'];kind=element['kind'];esc=lambda v:html.escape(str(v),quote=True)
    attrs=dict(id=element['id'],**{'data-owner':element.get('owner') or 'annotation'})
    if kind=='TEXT':
        attrs.update(x=d['x'],y=d['y'],fill=element['fill'],**{'font-family':element.get('font_family','Arial, sans-serif'),'font-size':d['font_size'],'text-anchor':d['anchor']})
        return '<text '+ ' '.join(f'{k}="{esc(v)}"' for k,v in attrs.items())+'>'+esc(d['text'])+'</text>'
    attrs.update(fill=element['fill'],stroke=element['stroke'],**{'stroke-width':element['stroke_width']})
    dash=element.get('dash')
    if dash:attrs['stroke-dasharray']=dash
    if kind=='RECT':
        tag='rect';attrs.update({k:d[k] for k in ('x','y','width','height')})
    elif kind=='ELLIPSE':
        x,y,w,h=ellipse_rect(d);tag='ellipse';attrs.update(cx=x+w/2,cy=y+h/2,rx=w/2,ry=h/2)
    elif kind=='PATH':tag='path';attrs['d']=d['d']
    elif kind=='POLYLINE':tag='polyline';attrs['points']=' '.join(f'{p[0]},{p[1]}' for p in d['points'])
    else:raise GateError('SVG_GEOMETRY_UNSUPPORTED: '+kind)
    return '<'+tag+' '+' '.join(f'{k}="{esc(v)}"' for k,v in attrs.items())+'/>'
