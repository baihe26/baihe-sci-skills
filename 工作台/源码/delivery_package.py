"""Panel-level package checks and audience-facing provenance notes.

The manifest is local task evidence. It does not prove experimental identity by
filename, inspect an Origin graph, or turn an author's declaration into proof.
"""
from pathlib import Path, PureWindowsPath
from paths import read, save, sha, digest
from core import GateError, source, writable
from scientific_gate import indexed, resolve_file
import math, os, hashlib, copy


def page_content_signature(path, page):
    """Bind actual slide objects and their referenced media/embedded payloads.

    Relationship IDs and ZIP member names may change in a genuine page copy.
    They are replaced with dependency content signatures. Layout/master/theme
    rendering is deliberately not claimed by this comparison.
    """
    from pptx_tags import read_package,xml,relationships,part_target,NS,R
    parts=read_package(path);presentation='ppt/presentation.xml'
    slide_ids=xml(parts[presentation]).findall('p:sldIdLst/p:sldId',NS)
    if type(page)is not int or not 1<=page<=len(slide_ids):raise GateError('SOURCE_PAGE_INDEX_INVALID')
    rel=relationships(parts,presentation)[slide_ids[page-1].get('{'+R+'}id')]
    owner=part_target(presentation,rel.get('Target'));cache={}
    def dependency(owner, stack=()):
        if owner in cache:return cache[owner]
        if owner in stack:return 'cycle:'+owner.rsplit('/',1)[-1].rstrip('0123456789')
        data=parts[owner]
        if not owner.endswith('.xml'):
            result=hashlib.sha256(data).hexdigest()
        else:
            result=hashlib.sha256(repr(canonical(xml(data),owner,stack+(owner,))).encode('utf-8')).hexdigest()
        cache[owner]=result;return result
    def canonical(element, owner, stack):
        rels=relationships(parts,owner);attributes=[]
        for name,value in sorted(element.attrib.items()):
            if name.startswith('{'+R+'}'):
                r=rels.get(value)
                if r is None:raise GateError('SOURCE_PAGE_RELATIONSHIP_MISSING')
                value=('external:'+r.get('Target','')) if r.get('TargetMode')=='External' else dependency(part_target(owner,r.get('Target')),stack)
            attributes.append((name,value))
        # Prefix/attribute order and formatting whitespace are not content.
        return (element.tag,attributes,element.text if element.tag.endswith('}t') else (element.text or '').strip(),
                [canonical(child,owner,stack) for child in element])
    slide=xml(parts[owner]);content=slide.find('p:cSld',NS)
    if content is None:raise GateError('SOURCE_PAGE_CONTENT_MISSING')
    value=canonical(content,owner,(owner,))
    return dict(sha256=hashlib.sha256(repr(value).encode('utf-8')).hexdigest(),
        scope='Slide cSld objects and referenced payloads; layout/master/theme rendering still requires review')


def display_path(value, display_root=None):
    """Use an explicit reader-facing root, never silently expose an absolute path."""
    raw=str(value);p=Path(raw)
    if PureWindowsPath(raw).is_absolute() or p.is_absolute():
        if display_root:
            try:return str(PureWindowsPath(raw).relative_to(PureWindowsPath(display_root))).replace('\\','/')
            except ValueError:
                try:return p.resolve().relative_to(Path(display_root).resolve()).as_posix()
                except ValueError:raise GateError('NOTES_DISPLAY_ROOT_DOES_NOT_CONTAIN_SOURCE')
        raise GateError('NOTES_REQUIRE_RELATIVE_READER_PATH')
    if '..' in raw.replace('\\','/').split('/'):
        raise GateError('NOTES_PARENT_PATH_NOT_READER_FRIENDLY')
    return raw.replace('\\','/')


def load_source_catalog(manifest, base):
    """One versioned source table may serve notes and the delivered package."""
    ref=manifest.get('source_catalog')
    if ref:
        if manifest.get('sources'):raise GateError('SOURCE_CATALOG_AND_INLINE_SOURCES_CONFLICT')
        path=resolve_file(base,ref['path']);bound=source(path,ref['sha256']);catalog=read(path)
        if catalog.get('schema_version')!='delivery-source-catalog-0.1':raise GateError('SOURCE_CATALOG_VERSION_INVALID')
        return indexed(catalog['sources']),path.parent,bound
    return indexed(manifest.get('sources',[])),base,None


def summary_identity(row, base):
    """Check a declared summary source against the actual file/page/object scope."""
    if not row.get('title') or not row.get('version'):raise GateError('SUMMARY_TITLE_AND_VERSION_REQUIRED')
    ref=row.get('source_pptx')
    if not ref or not ref.get('sha256'):raise GateError('SUMMARY_SOURCE_FILE_BINDING_REQUIRED')
    path=resolve_file(base,ref['path']);bound=source(path,ref['sha256']);page=row.get('page')
    signature=page_content_signature(path,page)
    objects=row.get('object_ids',[])
    if not isinstance(objects,list) or any(not isinstance(v,str) or not v for v in objects) or len(set(objects))!=len(objects):raise GateError('SUMMARY_OBJECT_IDS_INVALID')
    if objects:
        from pptx import Presentation
        prs=Presentation(str(path));names=[]
        def walk(shapes):
            for shape in shapes:
                names.append(shape.name)
                if shape.shape_type==6:walk(shape.shapes)
        walk(prs.slides[page-1].shapes)
        if any(names.count(v)!=1 for v in objects):raise GateError('SUMMARY_OBJECT_MISSING_OR_AMBIGUOUS')
    source(path,bound['sha256'])
    identity=dict(source_sha256=bound['sha256'],original_page=page,object_ids=objects,
        page_content_sha256=signature['sha256'],title=row.get('title'),version=row.get('version'))
    return dict(source_id=row['id'],identity=identity,identity_sha256=digest(identity),source=bound,
        object_scope='NAMED_OBJECTS_ON_HASH_BOUND_PAGE' if objects else 'WHOLE_PAGE',description='HOST_VERIFIED_MEANING_NOT_INFERRED_FROM_PAGE')


def format_panel_notes(panel, sources, page_offset=None):
    """Compose factual sentences only from supplied facts; no generated scientific claim."""
    required=('label','title','meaning','processing')
    if any(not isinstance(panel.get(k),str) or not panel[k].strip() for k in required):
        raise GateError('PANEL_NOTES_MEANING_TITLE_AND_PROCESSING_REQUIRED')
    if page_offset is not None and (not isinstance(page_offset,(str,int)) or isinstance(page_offset,bool)):
        raise GateError('PAGE_OFFSET_MUST_BE_INTEGER_OR_SYMBOL')
    refs=panel.get('source_ids',[])
    if not refs or any(k not in sources for k in refs):raise GateError('PANEL_NOTES_SOURCE_UNRESOLVED')
    sentences=[f"{panel['label']}｜{panel['title']}。{panel['meaning'].rstrip('。')}。"]
    for key in refs:
        row=sources[key];kind=row.get('kind')
        if kind=='summary_ppt':
            if type(row.get('page')) is not int or row['page']<1 or not row.get('title') or not row.get('version') or not row.get('page_description'):
                raise GateError('SUMMARY_PAGE_VERSION_AND_CONTENT_REQUIRED')
            number=str(row['page'])
            if page_offset is not None:number+='+'+str(page_offset) if not isinstance(page_offset,int) or page_offset>=0 else str(page_offset)
            sentences.append(f"对应《{row['title']}》（{row['version']}）第 {number} 页：{row['page_description'].rstrip('。')}。")
        elif kind in ('raw_data','derived_data','source_project'):
            label={'raw_data':'原始数据','derived_data':'派生数据','source_project':'来源工程'}[kind]
            path=display_path(row.get('display_path',row.get('path','')),row.get('display_root'))
            if not path:raise GateError('SOURCE_DISPLAY_PATH_REQUIRED')
            sentences.append(f"{label}：{path}"+(f"，{row['locator']}" if row.get('locator') else '')+'。')
        elif kind=='thesis':
            if row.get('relationship') not in ('same_data','related_only','not_found','not_checked'):
                raise GateError('THESIS_RELATIONSHIP_REQUIRED')
            relation={'same_data':'毕业论文中有同一数据','related_only':'毕业论文有相关实验，但尚未确认是同一数据','not_found':'本轮检索范围内未找到毕业论文对应数据','not_checked':'尚未核对毕业论文对应情况'}[row['relationship']]
            if row['relationship'] in ('same_data','related_only') and (not row.get('title') or not row.get('locator')):
                raise GateError('THESIS_TITLE_AND_LOCATOR_REQUIRED')
            sentences.append(relation+(f"：《{row['title']}》{row['locator']}" if row.get('locator') else '')+'。')
        else:raise GateError('PANEL_NOTES_SOURCE_KIND_UNSUPPORTED')
    if panel.get('summary_context')=='specified_summary_missing' and not any(sources[k].get('kind')=='summary_ppt' for k in refs):
        reason=panel.get('absence_from_summary_reason')
        if not reason:raise GateError('ABSENCE_FROM_SUMMARY_EXPLANATION_REQUIRED')
        sentences.append('数据汇总 PPT 未包含此项：'+reason.rstrip('。')+'。')
    sentences.append('本次处理：'+panel['processing'].rstrip('。')+'。')
    return '\n'.join(sentences)


def _inside(root,value):
    if not isinstance(value,str) or not value:raise GateError('PACKAGE_RELATIVE_PATH_REQUIRED')
    p=Path(value)
    if p.is_absolute() or PureWindowsPath(value).is_absolute():raise GateError('PACKAGE_FILE_MUST_BE_RELATIVE')
    target=(root/p).resolve()
    if not target.is_relative_to(root):raise GateError('PACKAGE_DEPENDENCY_OUTSIDE_ROOT')
    return target


def verify_current_bindings(panel,files,root,current_decks=()):
    """Tie actual saved presentation media and existing native receipts to the package."""
    findings=[];pending=[];checks=[];roles=panel.get('files',{});identity=panel['id']
    def fail(kind,message):findings.append(dict(kind=kind,id=identity,message=message))
    def wait(kind,message):pending.append(dict(kind=kind,panel_id=identity,message=message))
    def get_file(key):
        if key not in files:raise GateError('BINDING_FILE_UNRESOLVED: '+str(key))
        return _inside(root,files[key]['path'])
    occurrences=panel.get('presentation_occurrences',[])
    if roles.get('final_figure') and current_decks and panel.get('destination') in ('main','supplement') and not occurrences:
        wait('presentation_panel_binding_missing','尚未核对此小图在当前 PPT 中的具体对象及其实际图片内容')
    for occurrence in occurrences:
        try:
            from pptx_tags import presentation_locations,read_package
            from reference_update import picture_state
            deck_id=occurrence['deck_file_id'];figure_id=occurrence['final_file_id']
            if current_decks and deck_id not in current_decks:raise GateError('PRESENTATION_IS_NOT_CURRENT_DECK')
            if figure_id not in roles.get('final_figure',[]):raise GateError('PRESENTATION_FIGURE_NOT_THIS_PANEL')
            deck,figure=get_file(deck_id),get_file(figure_id);parts=read_package(deck)
            matches=[r for r in presentation_locations(deck,parts) if r['slide_id']==occurrence['slide_id'] and r['object_id']==occurrence['object_id']]
            if len(matches)!=1:raise GateError('PRESENTATION_PANEL_MISSING_OR_AMBIGUOUS')
            state=picture_state(parts,matches[0]);matched=state['media_sha256']==sha(figure)
            checks.append(dict(kind='presentation_media',panel_id=identity,deck_file_id=deck_id,object_id=occurrence['object_id'],matches=matched))
            if not matched:fail('presentation_panel_media_conflict','当前 PPT 对象显示的图片与包内此小图最终图不是同一内容')
        except (KeyError,GateError,FileNotFoundError) as exc:fail('presentation_panel_evidence_invalid','当前 PPT 小图绑定无法核对：'+str(exc))
    bindings=panel.get('project_bindings',[])
    bound_projects=set()
    for binding in bindings:
        try:
            pid,fid,eid=binding['project_file_id'],binding['final_file_id'],binding['evidence_file_id']
            if pid not in roles.get('current_project',[]) or fid not in roles.get('final_figure',[]):raise GateError('PROJECT_BINDING_NOT_THIS_PANEL')
            project,figure,evidence=get_file(pid),get_file(fid),get_file(eid);record=read(evidence)
            if record.get('schema_version')!='native-plot-binding-0.1':raise GateError('PROJECT_BINDING_SCHEMA_UNSUPPORTED')
            if record.get('project',{}).get('sha256')!=sha(project):raise GateError('PROJECT_BINDING_WRONG_PROJECT_VERSION')
            exports=[r for r in record.get('exports',[]) if r.get('sha256')==sha(figure)]
            if not exports:raise GateError('PROJECT_BINDING_WRONG_EXPORT_VERSION')
            raw_hashes={sha(get_file(k)) for k in roles.get('raw_data',[])}
            input_hashes=raw_hashes|{sha(get_file(k)) for role in ('derived_data','display_data') for k in roles.get(role,[])}
            arrays=record.get('arrays',[])
            if arrays and any(r.get('source_sha256') not in input_hashes or (r.get('raw_source_sha256') and r['raw_source_sha256'] not in raw_hashes) for r in arrays):raise GateError('PROJECT_BINDING_WRONG_RAW_DATA')
            native=record.get('native_readback',{})
            sufficient=bool(arrays) and all(r.get('locator') and r.get('values_sha256') for r in arrays) and native.get('status')=='MATCH' and native.get('graph_bindings') and native.get('method') in ('origin_native','structured_array_readback')
            checks.append(dict(kind='project_export',panel_id=identity,project_file_id=pid,final_file_id=fid,evidence_file_id=eid,
                project_and_export_hashes_match=True,native_array_binding_recorded=bool(sufficient)))
            if sufficient:bound_projects.add(pid)
            else:wait('native_array_binding_incomplete','工程与导出文件版本已对应，但还缺少原生曲线/完整数组反读证据：'+files[pid]['path'])
        except (KeyError,GateError,FileNotFoundError,ValueError) as exc:fail('project_export_binding_conflict','当前工程、原始数据与最终图对应不上：'+str(exc))
    for pid in roles.get('current_project',[]):
        if pid not in bound_projects and not any(b.get('project_file_id')==pid for b in bindings):
            wait('current_project_binding_not_verified','尚未核对当前工程内实际曲线与此小图导出内容：'+files.get(pid,{}).get('path',str(pid)))
    return findings,pending,checks


def verify_package(manifest_path, out=None):
    manifest_path=Path(manifest_path).resolve();bound=source(manifest_path);m=read(manifest_path)
    if m.get('schema_version')!='research-delivery-0.1':raise GateError('PACKAGE_SCHEMA_UNSUPPORTED')
    root=resolve_file(manifest_path.parent,m.get('package_root','.')).resolve()
    if not root.is_dir():raise GateError('PACKAGE_ROOT_MISSING')
    panels=indexed(m.get('panels',[]));files=indexed(m.get('files',[]));findings=[];records=[];pending=[];page_checks=[];current_checks=[]
    catalog,catalog_base,catalog_ref=load_source_catalog(m,manifest_path.parent);summary_bindings={}
    for sid,row in catalog.items():
        if row.get('kind')=='summary_ppt':summary_bindings[sid]=summary_identity(row,catalog_base)
    if not panels:raise GateError('PACKAGE_PANELS_REQUIRED')
    def issue(kind,identity,message):findings.append(dict(kind=kind,id=identity,message=message))
    for deck_id in m.get('current_presentation_file_ids',[]):
        if deck_id not in files:issue('current_presentation_missing',str(deck_id),'当前 PPT 文件没有纳入交付包文件表')
    for key,row in files.items():
        path=_inside(root,row['path'])
        if not path.is_file():issue('missing_file',key,'包内缺少文件：'+row['path']);continue
        actual=sha(path)
        if not row.get('sha256'):issue('unbound_revision',key,'文件未绑定预期版本：'+row['path'])
        elif actual!=row['sha256']:issue('changed_file',key,'文件内容与本版记录不同：'+row['path'])
        if row.get('original_source'):
            ref=row['original_source'];original=resolve_file(manifest_path.parent,ref['path'])
            verified=source(original,ref.get('sha256'))
            if verified['sha256']!=actual:issue('original_copy_changed',key,'标为原始副本的文件内容与原件不同')
            if path.name!=original.name:issue('original_renamed',key,'原始副本未保留原文件名')
            if row.get('preserve_mtime',True) and abs(path.stat().st_mtime-original.stat().st_mtime)>2:
                issue('original_timestamp_changed',key,'原始副本未保留原件修改时间')
        for dep in row.get('dependencies',[]):
            if dep not in files:issue('untracked_dependency',key,'依赖文件没有纳入包内文件记录：'+str(dep))
        records.append(dict(id=key,path=row['path'],sha256=actual))
    for key,panel in panels.items():
        destination=panel.get('destination')
        if destination not in ('main','supplement','reserve','excluded'):issue('destination_required',key,'需说明该小图放正文、补充、备用或明确排除')
        if destination=='excluded':
            if not panel.get('reason') or not panel.get('authorization'):issue('exclusion_unexplained',key,'排除的数据缺少原因或授权记录')
            continue
        roles=panel.get('files',{})
        for role in panel.get('required_roles',m.get('required_roles',[])):
            if not roles.get(role):issue('missing_role',key,'缺少本轮要求的配套：'+role)
        for role,ids in roles.items():
            if not isinstance(ids,list) or not ids or any(v not in files for v in ids):issue('unresolved_panel_file',key,'配套文件指向不完整：'+role)
        fs,ps,cs=verify_current_bindings(panel,files,root,m.get('current_presentation_file_ids',[]))
        findings.extend(fs);pending.extend(ps);current_checks.extend(cs)
        for pair in panel.get('synchronized_pairs',[]):
            if len(pair)!=2 or any(v not in files for v in pair):issue('invalid_sync_pair',key,'同步图件记录无效');continue
            refs=[_inside(root,files[v]['path']) for v in pair]
            if all(p.is_file() for p in refs) and sha(refs[0])!=sha(refs[1]):issue('different_current_figures',key,'两个交付版本所用的当前图内容不同')
        for page in panel.get('source_pages',[]):
            page=dict(page)
            if page.get('source_id'):
                sid=page['source_id']
                if sid not in summary_bindings:issue('source_page_catalog_unresolved',key,'来源页指向的共同来源身份不存在');continue
                src=catalog[sid];binding=summary_bindings[sid]
                if ('original_page' in page and page['original_page']!=src['page']) or ('source_version' in page and page['source_version']!=src['version']):
                    issue('source_page_catalog_conflict',key,'来源页的页码或版本与共同来源表不一致');continue
                if page.get('source_pptx') and page['source_pptx'].get('sha256')!=binding['identity']['source_sha256']:
                    issue('source_page_catalog_conflict',key,'来源页的原汇总文件与共同来源表不一致');continue
                page.update(original_page=src['page'],source_version=src['version'],source_pptx=binding['source'])
            file_id=page.get('file_id')
            if file_id not in files:issue('source_page_missing',key,'缺少此小图对应的来源页 PPTX');continue
            p=_inside(root,files[file_id]['path'])
            if p.suffix.lower()!='.pptx':issue('source_page_not_editable_pptx',key,'来源页面不是 PPTX 文件')
            if not page.get('source_version') or type(page.get('original_page')) is not int or page['original_page']<1:
                issue('source_page_identity_missing',key,'来源页缺少原汇总版本或原页码')
            if p.is_file() and p.suffix.lower()=='.pptx':
                from pptx import Presentation
                try:
                    deck=Presentation(str(p));page_index=page.get('page_in_copy',1)
                    if type(page_index)is not int or not 1<=page_index<=len(deck.slides):issue('source_page_index_invalid',key,'来源页副本页码不存在')
                except Exception as exc:
                    # Report a corrupt copied page; never use its filename as evidence.
                    issue('source_page_unreadable',key,'来源页面无法打开：'+type(exc).__name__)
            original=page.get('source_pptx')
            if original and p.is_file():
                try:
                    source_path=resolve_file(manifest_path.parent,original['path']);source_ref=source(source_path,original['sha256'])
                    a=page_content_signature(source_path,page['original_page']);b=page_content_signature(p,page.get('page_in_copy',1))
                    matches=a['sha256']==b['sha256']
                    page_checks.append(dict(panel_id=key,file_id=file_id,original_page=page['original_page'],source=source_ref,
                        object_payloads_match=matches,original_signature=a,copy_signature=b,rendered_appearance='PENDING'))
                    if not matches:issue('source_page_content_mismatch',key,'来源页副本的实际对象或媒体与指定原页不同，可能是错页、错版本或修改过的页面')
                    source(source_path,source_ref['sha256'])
                except (GateError,KeyError,TypeError,ValueError) as exc:
                    issue('source_page_evidence_invalid',key,'原汇总页证据无法核对：'+str(exc))
            elif not original:
                pending.append(dict(panel_id=key,file_id=file_id,kind='original_page_content_not_verified',message='仅能确认来源页副本可打开；缺少指定原汇总文件，尚未逐页核对内容是否相同'))
    expected=set(m.get('expected_panel_ids',[]));unaccounted=expected-set(panels)
    for key in sorted(unaccounted):issue('panel_lost',key,'上一版或批准范围的小图在本版没有去向')
    for fig in m.get('figures',[]):
        ids=fig.get('panel_ids',[])
        if any(p not in panels for p in ids):issue('figure_panel_unresolved',fig.get('id',''),'大图包含未登记的小图')
        for p in ids:
            if p in panels and panels[p].get('figure_id')!=fig.get('id'):issue('figure_membership_conflict',p,'小图记录与当前大图记录不一致')
    unlisted=[]
    if m.get('audit_unlisted_files'):
        listed={_inside(root,r['path']) for r in files.values()}|{manifest_path}
        allowed={_inside(root,p) for p in m.get('allowed_extra_files',[])}
        unlisted=[p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.resolve() not in listed|allowed]
        for p in unlisted:issue('unlisted_file',p,'包内存在未登记文件，核对是否旧版本；程序没有删除')
    for row in records:source(_inside(root,row['path']),row['sha256'])
    notes_coverage={};notes_decks={};notes_requirement_decks={r.get('deck_file_id') for r in m.get('notes_requirements',[])}
    for notes_link in m.get('notes_records',[]):
        record_id,deck_id=notes_link.get('file_id'),notes_link.get('deck_file_id')
        if record_id not in files or deck_id not in files:issue('notes_record_unresolved',str(record_id),'备注记录或当前 PPT 未在包中登记');continue
        record_path=_inside(root,files[record_id]['path']);deck_path=_inside(root,files[deck_id]['path'])
        if not record_path.is_file() or not deck_path.is_file():continue
        record=read(record_path)
        if record.get('output',{}).get('sha256')!=sha(deck_path):issue('notes_deck_version_conflict',record_id,'备注记录对应的 PPT 不是包内当前版本')
        from pptx import Presentation
        deck=Presentation(str(deck_path))
        notes_decks[deck_id]=deck;covered_panels=set()
        note_slides=record.get('slides',[])
        if not isinstance(note_slides,list) or not note_slides:
            issue('notes_record_empty',record_id,'备注记录没有任何当前页；来源资料齐全不代表 PPT 已有备注')
            note_slides=[]
        seen=set()
        for slide in note_slides:
            number=slide.get('slide_index')
            if type(number)is not int or not 1<=number<=len(deck.slides):issue('notes_page_not_found',record_id,'备注记录指向的页不存在');continue
            if number in seen:issue('notes_page_record_duplicate',record_id,'同一页在备注记录中重复出现');continue
            seen.add(number)
            current_slide=deck.slides[number-1]
            actual_text=current_slide.notes_slide.notes_text_frame.text if current_slide.has_notes_slide else ''
            if actual_text!=slide.get('text'):issue('notes_actual_text_conflict',record_id,'当前 PPT 实际备注文字与来源备注记录不同')
            if not isinstance(slide.get('text'),str) or not slide['text'].strip() or not actual_text.strip():
                issue('notes_actual_page_empty',record_id,'要求核对的当前页实际没有备注文字：第 '+str(number)+' 页')
            panel_ids=slide.get('panel_ids',[])
            if not isinstance(panel_ids,list) or not panel_ids or len(set(panel_ids))!=len(panel_ids) or any(pid not in panels for pid in panel_ids):
                issue('notes_page_panel_ids_invalid',record_id,'当前页备注缺少有效的小图身份');continue
            blocks=slide.get('panel_notes',[])
            verified_ids=set()
            if blocks:
                block_ids=[b.get('panel_id') for b in blocks]
                if block_ids!=panel_ids or any(not isinstance(b.get('text'),str) or not b['text'].strip() for b in blocks):
                    issue('notes_panel_blocks_invalid',record_id,'逐小图备注文字与该页小图顺序或身份不一致')
                elif '\n\n'.join(b['text'] for b in blocks)!=actual_text:
                    issue('notes_panel_text_missing',record_id,'当前页没有完整保留记录中的逐小图备注文字')
                else:verified_ids=set(panel_ids)
            elif m.get('requires_notes_binding') or deck_id in notes_requirement_decks:
                pending.append(dict(kind='notes_panel_text_binding_missing',deck_file_id=deck_id,slide_index=number,message='已核到整页备注，但缺少每个小图对应的实际备注文字块，不能确认逐小图覆盖'))
            else:verified_ids=set(panel_ids)
            key=(deck_id,number)
            if key in notes_coverage and notes_coverage[key]!=verified_ids:issue('notes_page_records_conflict',record_id,'不同备注记录对同一当前页的小图覆盖不一致')
            notes_coverage[key]=verified_ids;covered_panels.update(panel_ids)
        actual_bindings=record.get('summary_bindings',{})
        for sid,observed in actual_bindings.items():
            if sid not in summary_bindings or observed.get('identity_sha256')!=summary_bindings[sid]['identity_sha256']:
                issue('notes_source_identity_conflict',sid,'备注所用原汇总文件、版本或页码与资料包来源不同')
        for panel_id in covered_panels:
            panel=panels[panel_id]
            expected_sources={p['source_id'] for p in panel.get('source_pages',[]) if p.get('source_id')}
            note_sources=set(record.get('panel_source_ids',{}).get(panel_id,[]))
            if expected_sources and not expected_sources<=note_sources:issue('notes_panel_sources_missing',panel_id,'备注未覆盖此小图在包内登记的来源页')
            if expected_sources and not expected_sources<=set(actual_bindings):issue('notes_source_binding_missing',panel_id,'备注缺少包内来源页的实际文件与内容签名')
    if m.get('requires_notes_binding') and not m.get('notes_records'):
        pending.append(dict(kind='notes_source_binding_not_verified',message='本包需要核对来源备注，但尚未提供对应当前 PPT 的来源备注记录'))
    requirements=m.get('notes_requirements',[])
    required_decks={r.get('deck_file_id') for r in m.get('notes_records',[]) if r.get('deck_file_id')} if m.get('requires_notes_binding') else set()
    if m.get('requires_notes_binding') and not requirements:required_decks.update(m.get('current_presentation_file_ids',[]))
    required_decks.update(notes_requirement_decks)
    for deck_id in required_decks:
        if deck_id not in notes_decks:issue('notes_record_for_current_deck_missing',str(deck_id),'需要备注的当前 PPT 缺少可核对的实际页记录')
    explicit_decks=set()
    for requirement in requirements:
        deck_id=requirement.get('deck_file_id');explicit_decks.add(deck_id)
        rows=requirement.get('slides',[])
        if deck_id not in files or not isinstance(rows,list) or not rows:
            issue('notes_requirement_scope_invalid',str(deck_id),'备注要求需要明确当前 PPT 和至少一个页/小图范围');continue
        required_pages=set()
        for row in rows:
            number=row.get('slide_index');ids=row.get('panel_ids',[])
            if type(number)is not int or number<1 or number in required_pages or not isinstance(ids,list) or not ids or any(pid not in panels for pid in ids):
                issue('notes_requirement_scope_invalid',str(deck_id),'备注要求中的页码或小图身份无效');continue
            required_pages.add(number)
            missing=set(ids)-notes_coverage.get((deck_id,number),set())
            if missing:issue('notes_required_panels_missing',str(deck_id),'第 '+str(number)+' 页缺少已核实的逐小图备注：'+', '.join(sorted(missing)))
    for deck_id in required_decks-explicit_decks:
        derived={}
        if deck_id in notes_decks:
            from pptx_tags import presentation_locations
            path=_inside(root,files[deck_id]['path']);locations=presentation_locations(path)
            page_by_part={str(s.part.partname).lstrip('/'):n for n,s in enumerate(notes_decks[deck_id].slides,1)}
            for panel_id,panel in panels.items():
                for occurrence in panel.get('presentation_occurrences',[]):
                    if occurrence.get('deck_file_id')!=deck_id:continue
                    matches=[v for v in locations if v['slide_id']==occurrence.get('slide_id') and v['object_id']==occurrence.get('object_id')]
                    if len(matches)==1:
                        number=page_by_part[matches[0]['slide_part']];derived.setdefault(number,set()).add(panel_id)
        if not derived:
            pending.append(dict(kind='notes_coverage_scope_missing',deck_file_id=deck_id,message='本版要求备注完整，但尚未说明哪些当前页必须包含哪些小图备注；请登记本版范围或提供实际小图对象位置'))
        for number,ids in derived.items():
            missing=ids-notes_coverage.get((deck_id,number),set())
            if missing:issue('notes_required_panels_missing',deck_id,'第 '+str(number)+' 页缺少实际小图对应的备注：'+', '.join(sorted(missing)))
    for row in summary_bindings.values():source(row['source']['path'],row['source']['sha256'])
    if catalog_ref:source(catalog_ref['path'],catalog_ref['sha256'])
    source(manifest_path,bound['sha256'])
    report=dict(status='PACKAGE_BINDINGS_PENDING' if not findings and pending else 'PACKAGE_RECORDS_MATCH' if not findings else 'PACKAGE_REQUIRES_REPAIR',manifest=bound,files=records,
        findings=findings,pending=pending,source_page_checks=page_checks,summary_bindings=summary_bindings,source_catalog=catalog_ref,unaccounted_panel_ids=sorted(unaccounted),unlisted_files=unlisted,source_files_modified=False,
        scope='Package versions, actual source-page content, saved PPT media and supplied native/array binding receipts when provided; not general experimental truth.',
        current_artifact_checks=current_checks,origin_graph_binding='RECEIPT_AND_INPUT_HASHES_CHECKED_WHEN_AVAILABLE_NOT_NATIVE_REOPEN',visual='PENDING',author_acceptance='PENDING')
    if out is not None:
        out=writable(out)
        if out.exists():raise FileExistsError(out)
        save(out/'交付包核对.json',report)
    return report


def write_notes(request_path, out):
    """Write requested source notes in a new PPTX, retaining all non-note parts verbatim."""
    from pptx import Presentation
    from pptx_tags import read_package,xml,serialized,rels_name
    import zipfile,io
    request_path=Path(request_path).resolve();m=read(request_path);request_ref=source(request_path)
    if not isinstance(m.get('slides'),list) or not m['slides']:raise GateError('NOTES_TARGET_SLIDES_REQUIRED')
    artifact=resolve_file(request_path.parent,m['artifact']['path']);original=source(artifact,m['artifact']['sha256'])
    from task_context import load_context,require_parent_match
    require_parent_match(load_context(),artifact)
    sources,sources_base,catalog_ref=load_source_catalog(m,request_path.parent)
    panels=indexed(m['panels']);prs=Presentation(str(artifact));before=read_package(artifact)
    used_sources={sid for row in m['slides'] for pid in row['panel_ids'] for sid in panels.get(pid,{}).get('source_ids',[])}
    summary_bindings={sid:summary_identity(sources[sid],sources_base) for sid in used_sources if sid in sources and sources[sid].get('kind')=='summary_ppt'}
    numbers=set();records=[];edited_notes=set()
    for row in m['slides']:
        n=row['slide_index']
        if type(n)is not int or n<1 or n>len(prs.slides) or n in numbers:raise GateError('NOTES_SLIDE_INVALID_OR_DUPLICATE')
        numbers.add(n);slide=prs.slides[n-1]
        had_notes=slide.has_notes_slide
        existing=slide.notes_slide.notes_text_frame.text
        if 'expected_notes' in row:
            if row['expected_notes']!=existing:raise GateError('MANUAL_NOTES_CONFLICT')
        elif had_notes or not row.get('allow_new_notes'):
            raise GateError('MANUAL_NOTES_CONFLICT: expected_notes must also bind an empty note')
        ids=row['panel_ids']
        if not ids or any(i not in panels for i in ids):raise GateError('NOTES_PANEL_UNRESOLVED')
        panel_notes=[dict(panel_id=i,text=format_panel_notes(panels[i],sources,m.get('page_offset')),source_ids=panels[i]['source_ids']) for i in ids]
        notes='\n\n'.join(b['text'] for b in panel_notes)
        slide.notes_slide.notes_text_frame.text=notes
        edited_notes.add(str(slide.notes_slide.part.partname).lstrip('/'))
        records.append(dict(slide_index=n,panel_ids=ids,text=notes,panel_notes=panel_notes))
    stream=io.BytesIO();prs.save(stream);stream.seek(0)
    with zipfile.ZipFile(stream) as z:generated={n:z.read(n) for n in z.namelist()}
    # Compose only note parts and note relationships. Original slides, media, chart,
    # embedding and existing extension bytes remain untouched.
    merged=dict(before)
    for name,blob in generated.items():
        if name in edited_notes or name in {rels_name(n) for n in edited_notes} or (name.startswith('ppt/notesMasters/') and name not in before):merged[name]=blob
    ns='http://schemas.openxmlformats.org/package/2006/relationships'
    for name,blob in generated.items():
        if name.endswith('.rels') and name not in merged and name.startswith('ppt/notes'):
            merged[name]=blob
        if name.endswith('.rels') and (name.startswith('ppt/slides/') or name=='ppt/_rels/presentation.xml.rels'):
            gen=xml(blob);old=xml(before[name]) if name in before else xml(('<Relationships xmlns="'+ns+'"/>').encode())
            existing_ids={r.get('Id') for r in old}
            for rel in gen:
                if rel.get('Type','').rsplit('/',1)[-1] not in ('notesSlide','notesMaster'):continue
                same=[r for r in old if r.get('Type')==rel.get('Type') and r.get('Target')==rel.get('Target')]
                if not same:
                    if rel.get('Id') in existing_ids:raise GateError('NOTES_RELATIONSHIP_ID_CONFLICT')
                    old.append(rel);existing_ids.add(rel.get('Id'))
            if len(old):merged[name]=serialized(old)
    types=xml(before['[Content_Types].xml']);names={e.get('PartName') for e in types}
    for e in xml(generated['[Content_Types].xml']):
        name=e.get('PartName','')
        if name.startswith(('/ppt/notesSlides/','/ppt/notesMasters/')) and name not in names:types.append(e)
    merged['[Content_Types].xml']=serialized(types)
    # A newly added notesMaster needs the presentation's notesMasterIdLst reference.
    pres=xml(before['ppt/presentation.xml']);genpres=xml(generated['ppt/presentation.xml'])
    from pptx.oxml.ns import qn
    if pres.find(qn('p:notesMasterIdLst')) is None and genpres.find(qn('p:notesMasterIdLst')) is not None:
        element=genpres.find(qn('p:notesMasterIdLst'));sld=pres.find(qn('p:sldIdLst'))
        pres.insert(list(pres).index(sld) if sld is not None else 0,element);merged['ppt/presentation.xml']=serialized(pres)
    source(artifact,original['sha256']);source(request_path,request_ref['sha256'])
    for row in summary_bindings.values():source(row['source']['path'],row['source']['sha256'])
    if catalog_ref:source(catalog_ref['path'],catalog_ref['sha256'])
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);target=out/(artifact.stem+'_来源备注.pptx')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in merged.items():z.writestr(name,blob)
    actual=Presentation(str(target))
    if any(actual.slides[r['slide_index']-1].notes_slide.notes_text_frame.text!=r['text'] for r in records):raise GateError('SAVED_NOTES_READBACK_CONFLICT')
    report=dict(status='NOTES_WRITTEN_TO_NEW_COPY',source=original,output=source(target),slides=records,source_catalog=catalog_ref,
        summary_bindings=summary_bindings,panel_source_ids={pid:panels[pid]['source_ids'] for row in records for pid in row['panel_ids']},
        source_files_modified=False,unchanged_slide_xml=all(merged[k]==v for k,v in before.items() if k.startswith('ppt/slides/') and k.endswith('.xml')),
        unchanged_media_and_embedded_projects=all(merged[k]==v for k,v in before.items() if k.startswith(('ppt/media/','ppt/embeddings/','ppt/charts/'))),
        native_reopen='NOT_PERFORMED',scientific_meaning='HOST_SUPPLIED_NOT_INFERRED',visual='PENDING')
    save(out/'来源备注记录.json',report);return report
