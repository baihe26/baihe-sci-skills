"""Saved-PPT geometry and text metrics; these are not rendered glyph bounds."""
import math
from pptx.oxml.ns import qn


IDENTITY = (1., 0., 0., 1., 0., 0.)


def compose(a, b):
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])


def point(m, x, y):
    return (m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5])


def rotation(angle, x, y, flip_h=False, flip_v=False):
    t = math.radians(angle); c, s = math.cos(t), math.sin(t)
    fx, fy = (-1 if flip_h else 1), (-1 if flip_v else 1)
    return compose((1,0,0,1,x,y), compose((c*fx,s*fx,-s*fy,c*fy,0,0),(1,0,0,1,-x,-y)))


def group_matrix(shape):
    xf = shape._element.find('p:grpSpPr/a:xfrm', {'p':qn('p:x')[1:].split('}')[0], 'a':qn('a:x')[1:].split('}')[0]})
    if xf is None:
        return IDENTITY
    off, ext, child, childext = [xf.find(qn('a:'+k)) for k in ('off','ext','chOff','chExt')]
    if any(x is None for x in (off,ext,child,childext)):
        return IDENTITY
    ew,eh,cw,ch = [float(e.get(k)) for e,k in ((ext,'cx'),(ext,'cy'),(childext,'cx'),(childext,'cy'))]
    if not cw or not ch:
        return IDENTITY
    x,y,cx,cy = [float(e.get(k)) for e,k in ((off,'x'),(off,'y'),(child,'x'),(child,'y'))]
    scale = (ew/cw,0,0,eh/ch,x-cx*ew/cw,y-cy*eh/ch)
    rot = rotation(float(xf.get('rot','0'))/60000,x+ew/2,y+eh/2,xf.get('flipH')=='1',xf.get('flipV')=='1')
    return compose(rot,scale)


def _size(node):
    return float(node.get('sz'))/100 if node is not None and node.get('sz') is not None else None


def _style_size(element, level):
    if element is None:
        return None
    for path in ('a:lvl'+str(level+1)+'pPr/a:defRPr','a:defPPr/a:defRPr'):
        size = _size(element.find(path, {'a':qn('a:x')[1:].split('}')[0]}))
        if size is not None:
            return size
    return None


def resolved_font(run, paragraph, shape, slide, prs):
    """Resolve explicit and common OOXML inheritance, without guessing a theme size."""
    size = _size(run._r.find(qn('a:rPr')))
    if size is not None:
        return size,'run'
    pp = paragraph._p.find(qn('a:pPr'))
    size = _size(pp.find(qn('a:defRPr')) if pp is not None else None)
    if size is not None:
        return size,'paragraph'
    level = paragraph.level
    body = shape._element.find(qn('p:txBody'))
    size = _style_size(body.find(qn('a:lstStyle')) if body is not None else None,level)
    if size is not None:
        return size,'shape_list_style'
    ph_type='other'
    if shape.is_placeholder:
        index = shape.placeholder_format.idx
        typ = shape.placeholder_format.type
        ph_type = 'title' if int(typ) in (1,3) else 'body' if int(typ) in (2,7) else 'other'
        for label, owner in (('layout',slide.slide_layout),('master',slide.slide_layout.slide_master)):
            matches=[p for p in owner.placeholders if p.placeholder_format.idx==index]
            if len(matches)==1:
                target=matches[0]
                if target.has_text_frame:
                    for p in target.text_frame.paragraphs:
                        if p.level==level:
                            props=p._p.find(qn('a:pPr'))
                            size=_size(props.find(qn('a:defRPr')) if props is not None else None)
                            if size is not None:return size,label+'_paragraph'
                    b=target._element.find(qn('p:txBody'))
                    size=_style_size(b.find(qn('a:lstStyle')) if b is not None else None,level)
                    if size is not None:return size,label+'_list_style'
    master = slide.slide_layout.slide_master._element
    tx=master.find(qn('p:txStyles'))
    size=_style_size(tx.find(qn('p:'+ph_type+'Style')) if tx is not None else None,level)
    if size is not None:return size,'master_'+ph_type+'_style'
    size=_style_size(prs._element.find(qn('p:defaultTextStyle')),level)
    return (size,'presentation_default' if size is not None else 'unresolved')


def _cover_kind(shape):
    if shape.shape_type==13:
        return 'picture_alpha_not_evaluated'
    try:
        if int(shape.fill.type)==1:
            fill=shape._element.find('.//'+qn('a:solidFill'))
            alpha=fill.find('.//'+qn('a:alpha')) if fill is not None else None
            if alpha is None or int(alpha.get('val'))==100000:
                # AutoShape outlines may be non-rectangular, so this remains a candidate.
                return 'opaque_fill_outline_not_evaluated'
    except (AttributeError,TypeError,ValueError):
        pass
    return None


def presentation_geometry(prs):
    pages=[]
    for n,slide in enumerate(prs.slides,1):
        result=[]
        def walk(shapes,parent=IDENTITY,ancestors=()):
            for shape in shapes:
                if shape.shape_type==6:
                    walk(shape.shapes,compose(parent,group_matrix(shape)),ancestors+(shape.name,))
                    continue
                x,y,w,h=shape.left,shape.top,shape.width,shape.height
                local=rotation(shape.rotation,x+w/2,y+h/2)
                matrix=compose(parent,local)
                corners=[point(matrix,a,b) for a,b in ((x,y),(x+w,y),(x,y+h),(x+w,y+h))]
                box=[min(p[0] for p in corners)/12700,min(p[1] for p in corners)/12700,max(p[0] for p in corners)/12700,max(p[1] for p in corners)/12700]
                sx=math.hypot(parent[0],parent[1]);sy=math.hypot(parent[2],parent[3])
                fonts=[];autofit=1.
                if shape.has_text_frame:
                    norm=shape.text_frame._txBody.bodyPr.find(qn('a:normAutofit'))
                    if norm is not None:autofit=float(norm.get('fontScale','100000'))/100000
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            if not run.text.strip():continue
                            size,origin=resolved_font(run,paragraph,shape,slide,prs)
                            rpr=run._r.find(qn('a:rPr'))
                            baseline=int(rpr.get('baseline','0')) if rpr is not None else 0
                            calibrated_by_xml=not ancestors and norm is None
                            fonts.append(dict(text=run.text,working_pt=size,effective_pt=size if size is not None and calibrated_by_xml else None,
                                geometric_estimate_pt=size*sy*autofit if size is not None else None,
                                size_evidence='UNGROUPED_DECLARED_SIZE' if calibrated_by_xml else 'NATIVE_CALIBRATION_REQUIRED',
                                origin=origin,baseline=baseline,autofit_scale=autofit,
                                font_family_declaration=run.font.name or paragraph.font.name,
                                glyph_fallback='NOT_RENDERED'))
                result.append(dict(object_id=shape.name,native_id=shape.shape_id,slide_index=n,bbox_pt=box,
                    group_path=list(ancestors),group_scale=[sx,sy],anisotropic_group=abs(sx-sy)>1e-6,
                    fonts=fonts,text=shape.text if shape.has_text_frame else '',cover_kind=_cover_kind(shape),
                    bounds_kind='TRANSFORMED_OBJECT_FRAME_NOT_RENDERED_GLYPHS',z_order=len(result)))
        walk(slide.shapes);pages.append(result)
    return pages
