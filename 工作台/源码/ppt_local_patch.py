"""Copy-only edits to selected saved PPT objects, without rebuilding the deck.

All package parts other than the selected slide XML keep their original bytes.
Existing notes, source-page provenance, media and embeddings are not rewritten.
"""
from pathlib import Path
import copy
import hashlib
import math
import zipfile
from lxml import etree as ET
from core import GateError, writable, source
from paths import read, save, sha, digest
from pptx_tags import P, A, R, NS, xml, serialized, read_package, relationships, part_target
from reference_update import native_element, canonical
from task_context import load_context, require_parent_match, check_stage

EMU_PT=12700
FONT_FIELDS={'font_name','font_latin','font_east_asian','font_complex_script'}
TEXT_FIELDS={'text','font_pt','runs',*FONT_FIELDS}


def run_fonts(run):
    props=run.find('a:rPr',NS)
    return {label:(props.find('a:'+tag,NS).get('typeface') if props is not None and props.find('a:'+tag,NS) is not None else None)
            for label,tag in (('latin','latin'),('east_asian','ea'),('complex_script','cs'))}


def slide_parts(parts):
    root=xml(parts['ppt/presentation.xml']);rels=relationships(parts,'ppt/presentation.xml');out=[]
    for item in root.findall('p:sldIdLst/p:sldId',NS):
        rel=rels.get(item.get('{'+R+'}id'))
        if rel is None or rel.get('Type')!=R+'/slide' or rel.get('TargetMode')=='External':raise GateError('LOCAL_EDIT_SLIDE_RELATION_INVALID')
        name=part_target('ppt/presentation.xml',rel.get('Target',''))
        if name not in parts:raise GateError('LOCAL_EDIT_SLIDE_PART_MISSING')
        out.append(name)
    return out


def object_hash(shape):
    parents=[canonical(p.find('p:grpSpPr',NS)) for p in shape.iterancestors() if p.tag=='{'+P+'}grpSp']
    return digest(dict(shape=canonical(shape),parent_transforms=parents))


def parent_transform(shape):
    sx=sy=1.0;tx=ty=0.0
    for parent in shape.iterancestors():
        if parent.tag!='{'+P+'}grpSp':continue
        transform=parent.find('p:grpSpPr/a:xfrm',NS)
        if transform is None or any(transform.get(k,'0') not in ('0','false') for k in ('rot','flipH','flipV')):
            raise GateError('LOCAL_EDIT_ROTATED_OR_COMPLEX_GROUP_REQUIRES_NATIVE_ROUTE')
        nodes={k:transform.find('a:'+k,NS) for k in ('off','ext','chOff','chExt')}
        if any(v is None for v in nodes.values()):raise GateError('LOCAL_EDIT_GROUP_TRANSFORM_MISSING')
        try:
            gx=int(nodes['ext'].get('cx'))/int(nodes['chExt'].get('cx'));gy=int(nodes['ext'].get('cy'))/int(nodes['chExt'].get('cy'))
            tx=(tx-int(nodes['chOff'].get('x')))*gx+int(nodes['off'].get('x'))
            ty=(ty-int(nodes['chOff'].get('y')))*gy+int(nodes['off'].get('y'));sx*=gx;sy*=gy
        except (ValueError,TypeError,ZeroDivisionError) as exc:raise GateError('LOCAL_EDIT_GROUP_TRANSFORM_INVALID') from exc
    if sx<=0 or sy<=0:raise GateError('LOCAL_EDIT_GROUP_SCALE_INVALID')
    return sx,sy,tx,ty


def shape_transform(shape):
    transform=shape.find('p:grpSpPr/a:xfrm',NS) if shape.tag=='{'+P+'}grpSp' else shape.find('p:spPr/a:xfrm',NS)
    if transform is None:raise GateError('LOCAL_EDIT_INHERITED_POSITION_REQUIRES_NATIVE_ROUTE')
    off=transform.find('a:off',NS)
    if off is None:raise GateError('LOCAL_EDIT_POSITION_MISSING')
    return transform,off


def inspect_ppt(path):
    path=Path(path).resolve();bound=source(path);parts=read_package(path);slides=[]
    for index,name in enumerate(slide_parts(parts),1):
        root=xml(parts[name]);rows=[]
        for prop in root.xpath('.//p:cNvPr',namespaces=NS):
            shape=prop.getparent().getparent()
            if shape.tag not in ('{'+P+'}sp','{'+P+'}pic','{'+P+'}cxnSp','{'+P+'}grpSp'):continue
            row=dict(shape_id=int(prop.get('id')),name=prop.get('name'),text=''.join(shape.xpath('./p:txBody/a:p//a:t/text()',namespaces=NS)),object_sha256=object_hash(shape))
            try:
                _,off=shape_transform(shape);sx,sy,tx,ty=parent_transform(shape)
                row['position_pt']=[(int(off.get('x'))*sx+tx)/EMU_PT,(int(off.get('y'))*sy+ty)/EMU_PT]
            except GateError as exc:row['position_note']=str(exc)
            row['runs']=[dict(paragraph_index=p_index,run_index=r_index,text=run.findtext('a:t','',NS),fonts=run_fonts(run),
                             font_pt=float(run.find('a:rPr',NS).get('sz'))/100 if run.find('a:rPr',NS) is not None and run.find('a:rPr',NS).get('sz') else None)
                         for p_index,p in enumerate(shape.findall('p:txBody/a:p',NS),1) for r_index,run in enumerate(p.findall('a:r',NS),1)]
            rows.append(row)
        slides.append(dict(slide_number=index,slide_part=name,objects=rows))
    source(path,bound['sha256'])
    return dict(source=bound,slides=slides,scope='SAVED_OBJECTS_ONLY_UNSAVED_APP_STATE_NOT_OBSERVED')


def positive_number(value,field):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise GateError('LOCAL_EDIT_POSITIVE_NUMBER_REQUIRED: '+field)
    return value


def run_style(run,fields):
    if 'text' in fields:
        if not isinstance(fields['text'],str) or any(c in fields['text'] for c in ('\n','\r','\v')):raise GateError('LOCAL_EDIT_SINGLE_RUN_TEXT_REQUIRED')
        text=run.find('a:t',NS)
        if text is None:raise GateError('LOCAL_EDIT_RUN_TEXT_MISSING')
        if 'expected_text' in fields and text.text!=fields['expected_text']:raise GateError('LOCAL_EDIT_RUN_TEXT_CONFLICT')
        text.text=fields['text']
    if not FONT_FIELDS.intersection(fields) and 'font_pt' not in fields:return
    props=run.find('a:rPr',NS)
    if props is None:props=ET.Element('{'+A+'}rPr');run.insert(0,props)
    if 'font_name' in fields and (FONT_FIELDS-{'font_name'}).intersection(fields):raise GateError('LOCAL_EDIT_AMBIGUOUS_GENERIC_AND_SCRIPT_FONT')
    fonts=({'latin':fields['font_name'],'ea':fields['font_name'],'cs':fields['font_name']} if 'font_name' in fields else
           {tag:fields[key] for key,tag in (('font_latin','latin'),('font_east_asian','ea'),('font_complex_script','cs')) if key in fields})
    order=['latin','ea','cs','sym','hlinkClick','hlinkMouseOver','rtl','extLst']
    for tag,name in fonts.items():
        if not isinstance(name,str) or not name.strip():raise GateError('LOCAL_EDIT_FONT_NAME_REQUIRED')
        node=props.find('a:'+tag,NS)
        if node is None:
            node=ET.Element('{'+A+'}'+tag)
            after=set(order[order.index(tag)+1:])
            index=next((i for i,c in enumerate(props) if ET.QName(c).localname in after),len(props));props.insert(index,node)
        node.set('typeface',name)
    if 'font_pt' in fields:
        # Deliberately no project-wide hardcoded font or integer-size policy.
        size=round(positive_number(fields['font_pt'],'font_pt')*100)
        if size<1:raise GateError('LOCAL_EDIT_FONT_SIZE_BELOW_OPENXML_PRECISION')
        props.set('sz',str(size))


def edit_text(shape,fields):
    paragraphs=shape.findall('p:txBody/a:p',NS)
    if not paragraphs:raise GateError('LOCAL_EDIT_TARGET_HAS_NO_TEXT')
    if 'runs' in fields:
        if set(fields)&(TEXT_FIELDS-{'runs'}):raise GateError('LOCAL_EDIT_AMBIGUOUS_RUN_AND_SHAPE_STYLE')
        if not isinstance(fields['runs'],list) or not fields['runs']:raise GateError('LOCAL_EDIT_RUN_CHANGES_REQUIRED')
        seen=set()
        for change in fields['runs']:
            key=(change.get('paragraph_index'),change.get('run_index'))
            if any(type(v) is not int or v<1 for v in key) or key in seen:raise GateError('LOCAL_EDIT_RUN_TARGET_INVALID')
            seen.add(key)
            if key[0]>len(paragraphs):raise GateError('LOCAL_EDIT_RUN_TARGET_MISSING')
            runs=paragraphs[key[0]-1].findall('a:r',NS)
            if key[1]>len(runs):raise GateError('LOCAL_EDIT_RUN_TARGET_MISSING')
            mutation={k:v for k,v in change.items() if k not in ('paragraph_index','run_index')}
            if not mutation or set(mutation)-({'text','font_pt','expected_text'}|FONT_FIELDS):raise GateError('LOCAL_EDIT_RUN_FIELD_UNSUPPORTED')
            run_style(runs[key[1]-1],mutation)
        return
    runs=[r for p in paragraphs for r in p.findall('a:r',NS)]
    if len(paragraphs)!=1 or len(runs)!=1 or paragraphs[0].find('a:fld',NS) is not None or paragraphs[0].find('a:br',NS) is not None:
        raise GateError('LOCAL_EDIT_COMPLEX_TEXT_USE_EXPLICIT_RUNS: 混排、多段或域不能压平成一个文本；请指定逐run修改或原生编辑。')
    run_style(runs[0],fields)


def edit_ppt(request_path,out):
    request_path=Path(request_path).resolve();request=read(request_path);request_ref=source(request_path)
    if request.get('schema_version')!='ppt-local-patch-0.1':raise GateError('LOCAL_EDIT_REQUEST_VERSION_REQUIRED')
    ref=request.get('source',{});path=Path(ref.get('path',''))
    path=(request_path.parent/path).resolve() if not path.is_absolute() else path.resolve()
    if not ref.get('sha256'):raise GateError('LOCAL_EDIT_PARENT_HASH_REQUIRED')
    bound=source(path,ref['sha256']);context=load_context();require_parent_match(context,path)
    if context:check_stage(context,'local')
    out=writable(out,context)
    if out.exists():raise FileExistsError(out)
    if path.suffix.lower()!='.pptx':raise GateError('LOCAL_EDIT_PPTX_REQUIRED')
    if path==out or path.is_relative_to(out):raise GateError('LOCAL_EDIT_OUTPUT_OVERLAPS_SOURCE')
    parts=read_package(path)
    if any(k.startswith('_xmlsignatures/') for k in parts):raise GateError('LOCAL_EDIT_SIGNED_PACKAGE_REQUIRES_EXPLICIT_RESIGNING')
    slides=slide_parts(parts);requests=request.get('changes',[])
    if not isinstance(requests,list) or not requests:raise GateError('LOCAL_EDIT_CHANGES_REQUIRED')
    roots={};selected=set();events=[]
    for change in requests:
        page=change.get('slide_number');identity=change.get('shape_id')
        if type(page) is not int or not 1<=page<=len(slides) or type(identity) is not int or identity<1:raise GateError('LOCAL_EDIT_TARGET_INVALID')
        part=slides[page-1];key=(part,identity)
        if key in selected:raise GateError('LOCAL_EDIT_DUPLICATE_TARGET')
        selected.add(key)
        if part not in roots:roots[part]=xml(parts[part])
        shape=native_element(roots[part],identity)
        if shape.tag not in ('{'+P+'}sp','{'+P+'}pic','{'+P+'}cxnSp','{'+P+'}grpSp'):raise GateError('LOCAL_EDIT_TARGET_NATIVE_ROUTE_REQUIRED')
        before=object_hash(native_element(xml(parts[part]),identity))
        if change.get('expected_object_sha256') and change['expected_object_sha256']!=before:raise GateError('LOCAL_EDIT_OBJECT_CHANGED')
        fields=change.get('fields',{})
        if not fields or set(fields)-(TEXT_FIELDS|{'position_pt','move_pt'}):raise GateError('LOCAL_EDIT_FIELD_UNSUPPORTED')
        if set(fields)&TEXT_FIELDS:edit_text(shape,fields)
        if 'position_pt' in fields or 'move_pt' in fields:
            if 'position_pt' in fields and 'move_pt' in fields:raise GateError('LOCAL_EDIT_AMBIGUOUS_POSITION')
            name='position_pt' if 'position_pt' in fields else 'move_pt';value=fields[name]
            if not isinstance(value,list) or len(value)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value):raise GateError('LOCAL_EDIT_POSITION_INVALID')
            transform,off=shape_transform(shape);sx,sy,tx,ty=parent_transform(shape)
            if name=='position_pt':coords=[(value[0]*EMU_PT-tx)/sx,(value[1]*EMU_PT-ty)/sy]
            else:coords=[int(off.get('x'))+value[0]*EMU_PT/sx,int(off.get('y'))+value[1]*EMU_PT/sy]
            off.set('x',str(round(coords[0])));off.set('y',str(round(coords[1])))
        events.append(dict(slide_number=page,shape_id=identity,fields=sorted(fields),before=before,after=object_hash(shape)))
    # Compare each changed slide after removing only the explicitly selected shape.
    # This protects all other objects and slide metadata even on the same page.
    for part,root in roots.items():
        oldroot=xml(parts[part]);newroot=copy.deepcopy(root)
        ids=sorted([key[1] for key in selected if key[0]==part],key=lambda i:len(list(native_element(root,i).iterancestors())),reverse=True)
        for identity in ids:
            for tree in (oldroot,newroot):
                node=native_element(tree,identity);node.getparent().remove(node)
        if canonical(oldroot)!=canonical(newroot):raise GateError('LOCAL_EDIT_UNRELATED_SLIDE_CONTENT_CHANGED')
    changed={part:serialized(root) for part,root in roots.items()}
    for event in events:
        shape=native_element(roots[slides[event['slide_number']-1]],event['shape_id']);event['after']=object_hash(shape)
        event['observed_run_fonts']=[dict(paragraph_index=p_index,run_index=r_index,fonts=run_fonts(run))
                                     for p_index,p in enumerate(shape.findall('p:txBody/a:p',NS),1) for r_index,run in enumerate(p.findall('a:r',NS),1)]
    if all(parts[name]==blob for name,blob in changed.items()) or all(e['before']==e['after'] for e in events):raise GateError('LOCAL_EDIT_NO_ACTUAL_CHANGE')
    source(path,bound['sha256']);source(request_path,request_ref['sha256']);require_parent_match(context,path)
    out.mkdir(parents=True);target=out/(path.stem+'_修订版.pptx')
    with zipfile.ZipFile(path) as original,zipfile.ZipFile(target,'x') as revised:
        for info in original.infolist():revised.writestr(info,changed.get(info.filename,parts[info.filename]))
        revised.comment=original.comment
    final=read_package(target)
    if set(final)!=set(parts) or any(final[k]!=parts[k] for k in parts if k not in changed):raise GateError('LOCAL_EDIT_UNRELATED_PACKAGE_PART_CHANGED')
    source(path,bound['sha256'])
    report=dict(status='SAVED_COPY_PENDING_NATIVE_REVIEW',file=source(target),source=bound,request=request_ref,changes=events,
                changed_parts=sorted(changed),untouched_parts_preserved=len(parts)-len(changed),source_unchanged=True,
                notes_media_embeddings='ORIGINAL_PACKAGE_BYTES_PRESERVED',native_reopen='PENDING',visual_review='PENDING',
                scientific_content='ONLY_EXPLICIT_TEXT_AND_DISPLAY_CHANGES_NO_NEW_SCIENTIFIC_ASSERTION_CHECK')
    save(out/'局部修订记录.json',report);return report
