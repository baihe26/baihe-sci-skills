from paths import *
import uuid, datetime, re
class GateError(ValueError): pass
def writable(p,context=None):
    p=Path(p).resolve()
    from task_context import load_context, output_allowed
    context=context or load_context()
    if context:
        # Protection applies even inside the legacy workbench root.
        for item in context.get('protected_paths',[]):
            protected=Path(item).resolve()
            if p==protected or p.is_relative_to(protected) or protected.is_relative_to(p):
                raise GateError('OUTPUT_OVERLAPS_PROTECTED_SOURCE')
    if not p.is_relative_to(ROOT.resolve()) and not(context and output_allowed(p,context)):
        raise GateError('OUTPUT_OUTSIDE_ISOLATED_WORKSPACE')
    return p
def source(p,expected=None):
    p=Path(p).resolve()
    if not p.is_file():raise GateError('SOURCE_MISSING: '+str(p))
    h=sha(p)
    if expected and expected!=h:raise GateError('SOURCE_HASH_CONFLICT')
    return dict(path=str(p),sha256=h)
def route(text,explicit=None,stage=None):
    # Deliberately conservative, no scientific inference from filenames/column counts.
    if explicit:
        modules=[explicit] if isinstance(explicit,str) else list(explicit)
        if not modules or any(m not in ('plot','designer','vector','ppt','local','update') for m in modules):raise GateError('UNKNOWN_EXPLICIT_MODULE')
        if stage in ('understand','review'):raise GateError('READ_ONLY_STAGE_NO_PRODUCTION_ROUTE')
        if stage=='design' and modules!=['designer']:raise GateError('DESIGN_ONLY_NO_PRODUCTION')
        return list(dict.fromkeys(modules))
    if any(x in text for x in ('只改','局部修改','只修改')):return ['local']
    if any(x in text for x in ('更新引用','总稿和小稿','同步引用')):return ['update']
    if any(x in text for x in ('先不画','只设计','设计到此')):return ['designer']
    if any(x in text for x in ('重建','别重新设计','可编辑矢量','批准SceneGraph','按已批准')):return ['vector']
    if any(x in text for x in ('只PPT','排成汇报','现成图','制作PPT','小PPT')):return ['ppt']
    if any(x in text for x in ('只作图','只画图','表画成图','数据图')):return ['plot']
    if '整个实验' in text:return ['plot','designer','vector','ppt']
    raise GateError('INTENT_NEEDS_CLARIFICATION: 请说明只作图、只设计、重建、按设计生产或只PPT')
def new_task(intent,project_id,inputs=(),request_id=None,modules=None,context=None):
    if not project_id.strip():raise GateError('PROJECT_ID_REQUIRED')
    rid=request_id or uuid.uuid4().hex
    if not re.fullmatch(r'[\w.-]{1,80}',rid):raise GateError('INVALID_REQUEST_ID')
    dest=writable(ROOT/'任务'/rid)
    if dest.exists():raise GateError('DUPLICATE_REQUEST_OR_OUTCOME_UNKNOWN: 读取原任务，不自动重放')
    rows=[source(p) for p in inputs]
    modules=route(intent,modules,context.get('stage') if context else None)
    dest.mkdir(parents=True)
    state=dict(schema_version='coordination-envelope-0.1',task_id=rid,project_id=project_id,intent=intent,modules=modules,
       created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=rows,contract_refs=[],assets=[],references=[],parent_revision=None,
       human_overrides=[],pending_decisions=[],impact=[],validation=dict(input_protection='HASH_BOUND',scientific_review='PENDING',author_acceptance='PENDING'),
       status='INPUT_REQUIRED' if not inputs else 'READY_FOR_CONTRACT_MAPPING')
    if context:
        state.update(stage=context['stage'],parent_revision=context.get('parent'),
                     task_context=dict(path=context['_file'],sha256=context['_sha256']),
                     preferences=context.get('resolved_preferences',context.get('preferences',{})),
                     author_profile_source=context.get('author_profile_source'),delivery_modes=context.get('delivery_modes',[]))
    save(dest/'任务记录.json',state)
    from ledger import emit
    emit('TASK_CREATED',rid,dict(project_id=project_id,modules=modules,state_path=str(dest/'任务记录.json'),state_sha256=sha(dest/'任务记录.json')))
    return state
def readable(font_pt,source_width_mm,insert_width_pt,min_pt=16):
    if min(font_pt,source_width_mm,insert_width_pt)<=0:raise GateError('INVALID_PHYSICAL_SIZE')
    actual=font_pt*insert_width_pt/(source_width_mm*72/25.4)
    return dict(effective_pt=round(actual,3),minimum_pt=min_pt,status='PASS' if actual>=min_pt else 'SPLIT_OR_DISPLAY_VARIANT_REQUIRED',method='真实物理尺寸比例；仍需整页视觉检查')
def visibility(required,deliveries,omitted=()):
    missing=[]
    for identity in required:
        if identity in omitted:continue
        matches=deliveries.get(identity,[])
        if not matches or not any(Path(m['path']).is_file() and m.get('visible') is True for m in matches):missing.append(identity)
    return dict(status='PASS' if not missing else 'FAIL',missing=missing,explicitly_omitted=list(omitted),scope='定位记录及交付物存在性；内容须原生/视觉核查')
def impact(references,asset_id,new_revision,observed):
    out=[]
    for r in references:
        if r['asset_id']!=asset_id:continue
        current=observed.get(r['reference_id'])
        status='CONFLICT' if r.get('manual_override') or current!=r['object_digest'] else 'UPDATE_REQUIRED'
        out.append(dict(**r,target_revision=new_revision,update_status=status))
    return out
def semantic_signature(contract,spec):
    """Display-only revisions cannot change labels, units, n, denominator, bindings or error."""
    keys=('scientific_question','experimental_unit','identifiers','nesting_structure','point_semantics','statistical_n','x_variable','y_variable','design','connection','connection_keys','summary','uncertainty','normalization','denominator','source','plot_data','analysis','plot_bindings')
    return digest(dict(contract={k:contract.get(k,'not_recorded') for k in keys},labels={k:spec.get(k,'not_recorded') for k in ('x_title','y_title','x_scale','y_scale','x_limits','y_limits')},groups=spec['groups']))
def require_display_equivalent(old_contract,old_spec,new_contract,new_spec,display_permissions=None):
    # The strict legacy path is unchanged. Explicit mappings may rename a stable
    # group or re-encode its display without changing samples, units or bindings.
    import copy
    candidate=copy.deepcopy(new_spec)
    permissions=display_permissions or {}
    if permissions:
        if not permissions.get('reason'):raise GateError('DISPLAY_PERMISSION_REASON_REQUIRED')
        old_groups=old_spec.get('groups',{});new_groups=candidate.get('groups',{})
        if not isinstance(old_groups,dict) or not isinstance(new_groups,dict) or set(old_groups)!=set(new_groups):
            raise GateError('STABLE_GROUP_IDENTITIES_REQUIRED')
        aliases=permissions.get('group_aliases',{})
        encoding=permissions.get('group_styles',{})
        if not set(aliases)<=set(old_groups) or not set(encoding)<=set(old_groups):raise GateError('DISPLAY_GROUP_UNKNOWN')
        for key,values in new_groups.items():
            for field in ('label','color','line_style','marker','line_width'):
                if values.get(field)==old_groups[key].get(field):continue
                permit=aliases.get(key) if field=='label' else encoding.get(key,{}).get(field)
                if not isinstance(permit,dict) or permit.get('before')!=old_groups[key].get(field) or permit.get('after')!=values.get(field):
                    raise GateError('DISPLAY_MAPPING_NOT_AUTHORIZED: '+key+'.'+field)
                if field in old_groups[key]:values[field]=old_groups[key][field]
                else:values.pop(field,None)
    if semantic_signature(old_contract,old_spec)!=semantic_signature(new_contract,candidate):raise GateError('SCIENTIFIC_SEMANTICS_CHANGED: 标签/单位/n/误差/分母/绑定变化，不能按显示更新传播')
    return True
