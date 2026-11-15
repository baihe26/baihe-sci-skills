"""Editable subset of absolute SVG paths for native PresentationML geometry.

Unsupported commands are handed off, never sampled into a raster or a polyline.
"""
import math
import re
from core import GateError

TOKEN=re.compile(r'[A-Za-z]|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
COUNTS={'M':2,'L':2,'C':6,'Q':4,'Z':0}


def path_commands(value):
    if not isinstance(value,str) or not value.strip():raise GateError('EDITABLE_PATH_DATA_REQUIRED')
    if TOKEN.sub('',value).replace(',','').strip():raise GateError('EDITABLE_PATH_INVALID_TOKEN')
    tokens=TOKEN.findall(value);result=[];i=0;command=None
    while i<len(tokens):
        if tokens[i].isalpha():
            command=tokens[i];i+=1
            if command not in COUNTS:raise GateError('EDITABLE_PATH_COMMAND_REQUIRES_ILLUSTRATOR: '+command)
        elif command is None:raise GateError('EDITABLE_PATH_COMMAND_REQUIRED')
        n=COUNTS[command]
        if i+n>len(tokens):raise GateError('EDITABLE_PATH_ARGUMENTS_MISSING')
        try:values=[float(v) for v in tokens[i:i+n]]
        except ValueError as e:raise GateError('EDITABLE_PATH_ARGUMENT_INVALID') from e
        if any(not math.isfinite(v) for v in values):raise GateError('EDITABLE_PATH_NUMBER_INVALID')
        result.append((command,values));i+=n
        if command=='M':command='L'
        elif command=='Z':command=None
    if not result or result[0][0]!='M':raise GateError('EDITABLE_PATH_MUST_BEGIN_MOVE')
    return result


def draw_path(slide, data, box, scale):
    """Return an editable shape with cubic/quadratic control points intact."""
    from pptx.util import Pt
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
    from pptx.oxml.xmlchemy import OxmlElement
    commands=path_commands(data.get('d'))
    x0,y0,x1,y1=box
    if x1<=x0 or y1<=y0:raise GateError('EDITABLE_PATH_POSITIVE_BOUNDS_REQUIRED')
    shape=slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE,Pt(x0*scale),Pt(y0*scale),Pt((x1-x0)*scale),Pt((y1-y0)*scale))
    ns='{http://schemas.openxmlformats.org/drawingml/2006/main}'
    sppr=shape.element.find('{http://schemas.openxmlformats.org/presentationml/2006/main}spPr')
    preset=sppr.find(ns+'prstGeom');sppr.remove(preset)
    custom=OxmlElement('a:custGeom')
    for name in ('avLst','gdLst','ahLst','cxnLst'):custom.append(OxmlElement('a:'+name))
    rect=OxmlElement('a:rect')
    for key,val in [('l','0'),('t','0'),('r','r'),('b','b')]:rect.set(key,val)
    custom.append(rect)
    paths=OxmlElement('a:pathLst');path=OxmlElement('a:path')
    path.set('w',str(round((x1-x0)*1000)));path.set('h',str(round((y1-y0)*1000)))
    tags={'M':'moveTo','L':'lnTo','C':'cubicBezTo','Q':'quadBezTo','Z':'close'}
    for command,values in commands:
        node=OxmlElement('a:'+tags[command])
        for j in range(0,len(values),2):
            point=OxmlElement('a:pt');point.set('x',str(round((values[j]-x0)*1000)));point.set('y',str(round((values[j+1]-y0)*1000)));node.append(point)
        path.append(node)
    paths.append(path);custom.append(paths);sppr.insert(1,custom)
    return shape
