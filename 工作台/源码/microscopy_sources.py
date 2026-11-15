"""Read PPT image displays, not just media bytes; do not process experimental pixels."""
import hashlib
import math
from pathlib import Path, PurePosixPath
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from core import GateError, writable
from paths import read, save, sha

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
REL='http://schemas.openxmlformats.org/package/2006/relationships'


def _semantic_xml(node):
    if node is None:return None
    return dict(tag=node.tag,attributes=dict(sorted(node.attrib.items())),text=(node.text or '').strip(),
                children=[_semantic_xml(x) for x in node])


def _relationships(z, part):
    rel=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
    if rel not in z.namelist():return {}
    result={}
    for row in ET.fromstring(z.read(rel)):
        target=row.get('Target','')
        result[row.get('Id')]=dict(external=row.get('TargetMode')=='External',
            path=posixpath.normpath(posixpath.join(posixpath.dirname(part),target)) if not target.startswith('/') else target.lstrip('/'))
    return result


def inspect_microscopy(pptx, pages=None):
    pptx=Path(pptx).resolve();records=[]
    selected=None if pages is None else set(pages)
    if selected is not None and any(type(p) is not int or p<1 for p in selected):raise GateError('SOURCE_PAGE_INVALID')
    with zipfile.ZipFile(pptx) as z:
        presentation=ET.fromstring(z.read('ppt/presentation.xml'))
        rels=_relationships(z,'ppt/presentation.xml')
        ids=presentation.findall('p:sldIdLst/p:sldId',NS)
        if selected and max(selected)>len(ids):raise GateError('SOURCE_PAGE_NOT_FOUND')
        for number,item in enumerate(ids,1):
            if selected is not None and number not in selected:continue
            part=rels[item.get('{'+NS['r']+'}id')]['path']
            root=ET.fromstring(z.read(part));image_rels=_relationships(z,part)
            def visit(container,groups):
                for shape in container:
                    if shape.tag=='{'+NS['p']+'}grpSp':
                        visit(shape,groups+[_semantic_xml(shape.find('p:grpSpPr/a:xfrm',NS))])
                    elif shape.tag=='{'+NS['p']+'}pic':
                        info=shape.find('p:nvPicPr/p:cNvPr',NS);blip=shape.find('p:blipFill/a:blip',NS)
                        if blip is None:continue
                        relation=image_rels.get(blip.get('{'+NS['r']+'}embed') or blip.get('{'+NS['r']+'}link'),{})
                        media=relation.get('path');external=relation.get('external',False)
                        raw=None if external or media not in z.namelist() else z.read(media)
                        display=dict(crop=_semantic_xml(shape.find('p:blipFill/a:srcRect',NS)),
                            image_effects=[_semantic_xml(x) for x in blip],
                            fill=_semantic_xml(shape.find('p:blipFill/a:stretch',NS)),
                            transform=_semantic_xml(shape.find('p:spPr/a:xfrm',NS)),group_transforms=groups,
                            shape_effects=_semantic_xml(shape.find('p:spPr/a:effectLst',NS)))
                        records.append(dict(page=number,object_id=info.get('id') if info is not None else None,
                            object_name=info.get('name') if info is not None else None,media_part=media,
                            media_sha256=hashlib.sha256(raw).hexdigest() if raw else None,
                            external_link=external,display=display,
                            display_status='RECORDED_RENDER_COMPARISON_REQUIRED'))
            tree=root.find('p:cSld/p:spTree',NS)
            if tree is not None:visit(tree,[])
    return dict(source=dict(path=str(pptx),sha256=sha(pptx)),images=records,
                scope='原PPT对象的显示设置；未修改实验像素，未把媒体文件等同于页面实际显示。')


def compare_displays(parent, current, allowed_changes=()):
    findings=[]
    if 'transform' in allowed_changes or 'group_transforms' in allowed_changes:
        raise GateError('DISPLAY_TRANSFORM_PERMISSION_TOO_BROAD: 请分别指定translate、uniform_scale、rotation、flip或对应group_操作。')
    for field in ('media_sha256',):
        if parent.get(field)!=current.get(field) and field not in allowed_changes:
            findings.append(dict(kind='SOURCE_IMAGE_CHANGED',field=field))
    for field in ('crop','image_effects','fill','shape_effects'):
        if parent['display'].get(field)!=current['display'].get(field) and field not in allowed_changes:
            findings.append(dict(kind='DISPLAY_INHERITANCE_CHANGED',field=field))
    def transform_fields(old,new,prefix=''):
        if old==new:return
        if old is None or new is None:
            findings.append(dict(kind='TRANSFORM_STRUCTURE_CHANGED',field=prefix+'transform'));return
        oa,na=old.get('attributes',{}),new.get('attributes',{})
        for field,permission in (('rot','rotation'),('flipH','flip'),('flipV','flip')):
            if oa.get(field,'0')!=na.get(field,'0') and prefix+permission not in allowed_changes:
                findings.append(dict(kind='DISPLAY_TRANSFORM_CHANGED',field=prefix+field))
        other=set(oa)|set(na)-{'rot','flipH','flipV'}
        for key in other-{'rot','flipH','flipV'}:
            if oa.get(key)!=na.get(key):findings.append(dict(kind='TRANSFORM_ATTRIBUTE_CHANGED',field=prefix+key))
        oc={x['tag'].rsplit('}',1)[-1]:x for x in old.get('children',[])}
        nc={x['tag'].rsplit('}',1)[-1]:x for x in new.get('children',[])}
        for key in set(oc)|set(nc):
            if oc.get(key)==nc.get(key):continue
            if key in ('off','chOff') and prefix+'translate' in allowed_changes:continue
            if key in ('ext','chExt') and prefix+'uniform_scale' in allowed_changes and key in oc and key in nc:
                a,b=oc[key]['attributes'],nc[key]['attributes']
                try:
                    sx=float(b['cx'])/float(a['cx']);sy=float(b['cy'])/float(a['cy'])
                    if sx>0 and math.isclose(sx,sy,rel_tol=1e-8,abs_tol=1e-10):continue
                except (KeyError,ValueError,ZeroDivisionError):pass
            findings.append(dict(kind='DISPLAY_TRANSFORM_CHANGED',field=prefix+key))
    transform_fields(parent['display'].get('transform'),current['display'].get('transform'))
    old_groups,new_groups=parent['display'].get('group_transforms',[]),current['display'].get('group_transforms',[])
    if len(old_groups)!=len(new_groups):findings.append(dict(kind='GROUP_HIERARCHY_CHANGED',field='group_transforms'))
    else:
        for old,new in zip(old_groups,new_groups):transform_fields(old,new,'group_')
    return dict(status='FAIL' if findings else 'PASS',findings=findings,
                visual_acceptance='RENDER_REVIEW_REQUIRED')


def scale_bar_check(calibration, crop_width_px, display_width_mm, bar_length_mm, label_value, tolerance=0.02):
    """All lengths in one stated physical unit. A resized field alone is not an error."""
    numbers=[calibration.get('instrument_bar_px'),calibration.get('instrument_bar_value'),
             crop_width_px,display_width_mm,bar_length_mm,label_value]
    if not calibration.get('unit') or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in numbers):
        raise GateError('SCALIBAR_CALIBRATION_REQUIRED')
    if not math.isfinite(tolerance) or tolerance<0:raise GateError('SCALIBAR_TOLERANCE_INVALID')
    value_per_px=calibration['instrument_bar_value']/calibration['instrument_bar_px']
    source_px=bar_length_mm/display_width_mm*crop_width_px
    represented=source_px*value_per_px
    error=abs(represented/label_value-1)
    return dict(status='PASS' if error<=tolerance else 'CHECK_CALIBRATION',represented_value=represented,
                label_value=label_value,unit=calibration['unit'],relative_error=error,
                scope='已给定原仪器标定、裁剪与横向等比显示；非等比/旋转测量须先换算到对应轴。')


def inspect_request(request_path,out=None):
    p=Path(request_path).resolve();request=read(p)
    source=Path(request['pptx']);source=source if source.is_absolute() else p.parent/source
    result=inspect_microscopy(source,request.get('pages'))
    result['status']='DISPLAY_PROVENANCE_RECORDED'
    if out:
        folder=writable(out)
        if folder.exists():raise FileExistsError(folder)
        save(folder/'显微图来源与显示.json',result)
    return result
