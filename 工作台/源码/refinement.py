"""Apply a reviewed, display-only patch into a new immutable revision."""
from paths import Path,read,save,sha
from core import writable,GateError,source
from preflight import inspect_pack
from scientific_gate import resolve_file
from pack_files import dependency_paths
import copy,shutil,re,math


def _finite_list(value,length=None):
    if not isinstance(value,list) or length is not None and len(value)!=length or not value or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value):
        raise GateError('PATCH_GEOMETRY_INVALID')
    return value


def _geometry_patch(obj,element,key,value):
    kind=obj['geometry']['kind'];data=obj['geometry']['data'];box=obj['bbox']
    if key=='translate_px':
        dx,dy=_finite_list(value,2)
        if kind=='ELLIPSE' and 'cx' in data:
            data['cx']+=dx;data['cy']+=dy
        elif kind in ('RECT','ELLIPSE','TEXT'):
            data['x']+=dx;data['y']+=dy
        elif kind=='POLYLINE':data['points']=[[x+dx,y+dy] for x,y in data['points']]
        else:raise GateError('PATH_MOVE_REQUIRES_NATIVE_ROUTE')
        obj['bbox']=[box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy]
    elif key=='bbox_px':
        x,y,right,bottom=_finite_list(value,4)
        if kind not in ('RECT','ELLIPSE') or right<=x or bottom<=y:raise GateError('PATCH_RESIZE_PRIMITIVE_REQUIRED')
        if kind=='ELLIPSE' and 'cx' in data:data.update(cx=(x+right)/2,cy=(y+bottom)/2,rx=(right-x)/2,ry=(bottom-y)/2)
        else:data.update(x=x,y=y,width=right-x,height=bottom-y)
        obj['bbox']=list(value)
    else:
        if kind!='POLYLINE' or not isinstance(value,list) or len(value)<2:raise GateError('PATCH_POINTS_POLYLINE_REQUIRED')
        points=[_finite_list(p,2) for p in value]
        if points[0]==points[-1] and 'encoding' in data:raise GateError('PATCH_RELATION_ENDPOINTS_COINCIDENT')
        data['points']=copy.deepcopy(points);xs,ys=zip(*points);obj['bbox']=[min(xs),min(ys),max(xs),max(ys)]
    if element is not None:
        element['data']={k:copy.deepcopy(v) for k,v in data.items() if k!='dash'}
        x,y,r,b=obj['bbox'];element['bbox']=[x,y,r-x,b-y]
    if kind=='TEXT':
        # The frozen scene carries both the glyph data and convenience fields.
        obj['position']=[data['x'],data['y']] if 'position' in obj else obj.get('position')
        if obj.get('position') is None:obj.pop('position',None)


def _refresh_group_bounds(graph,plan):
    all_rows={o['id']:o for k in ('objects','text_objects','arrow_objects','groups') for o in graph[k]}
    pending={g['id']:g for g in graph['groups']};changed=[]
    while pending:
        progressed=False
        for identity,group in list(pending.items()):
            kids=[link['child_id'] for link in graph['parent_child'] if link['parent_id']==identity]
            if any(k in pending for k in kids):continue
            if kids:
                boxes=[all_rows[k]['bbox'] for k in kids];box=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
                if group['bbox']!=box:group['bbox']=box;changed.append(identity)
                for instance in plan['instances']:
                    if group['name'].endswith('__'+instance['id']):
                        x,y,r,b=box;instance['bbox']=[x,y,r-x,b-y]
            pending.pop(identity);progressed=True
        if not progressed:raise GateError('REVISION_PARENT_CYCLE')
    return changed


def _check_relation_endpoints(before,after,request):
    """Keep a rerouted arrow near its scientific owner, with reviewable gaps.

    Text/decoration geometry is not evidence of material identity. The explicit
    source and target group binding remains necessary; these proximity checks are
    a guard against pointing the same ID at another material, not scientific proof.
    """
    old_groups={g['id']:g['bbox'] for g in before['groups']};groups={g['id']:g['bbox'] for g in after['groups']}
    old_arrows={a['id']:a for a in before['arrow_objects']};records=[]
    approvals={r['object_id']:r for r in request.get('relation_endpoint_review',[])}
    def distance(point,box):
        return math.hypot(max(box[0]-point[0],0,point[0]-box[2]),max(box[1]-point[1],0,point[1]-box[3]))
    for arrow in after['arrow_objects']:
        old=old_arrows[arrow['id']];pts=arrow['geometry']['data']['points'];previous=old['geometry']['data']['points']
        for side,index in (('source',0),('target',-1)):
            owner=arrow[side+'_id'];box=groups[owner];point=pts[index]
            # A modest visual gap is allowed; larger one requires a current,
            # explicit endpoint review rather than silently changing the target.
            gap=max(distance(previous[index],old_groups[owner]),.1*math.hypot(box[2]-box[0],box[3]-box[1]))
            approval=approvals.get(arrow['id'])
            if approval:
                if approval.get('source_id')!=arrow['source_id'] or approval.get('target_id')!=arrow['target_id'] or not approval.get('reason'):
                    raise GateError('RELATION_ENDPOINT_REVIEW_IDENTITY_CONFLICT')
                requested=approval.get(side+'_maximum_gap_px',gap)
                if isinstance(requested,bool) or not isinstance(requested,(int,float)) or not math.isfinite(requested) or requested<0:raise GateError('RELATION_ENDPOINT_REVIEW_GAP_INVALID')
                gap=requested
            observed=distance(point,box)
            nearer=[identity for identity,b in groups.items() if identity!=owner and distance(point,b)+.001<observed]
            if observed>gap+.001 or nearer:raise GateError('RELATION_ENDPOINT_OWNER_CONFLICT: '+arrow['id']+'/'+side)
            records.append(dict(object_id=arrow['id'],endpoint=side,owner=owner,gap_px=observed,allowed_gap_px=gap))
    return records

def revise(scene_path,request_path,out):
    scene_path=Path(scene_path).resolve();request_path=Path(request_path).resolve();out=writable(out);base=scene_path.parent
    from task_context import load_context,require_parent_match
    require_parent_match(load_context(),scene_path)
    if out.exists():raise FileExistsError(out)
    inspection=inspect_pack(scene_path);request=read(request_path)
    if request['expected_parent_sha256']!=sha(scene_path):raise GateError('REVISION_PARENT_CONFLICT')
    if request.get('expected_pack_sha256')!=inspection['input_fingerprint']:raise GateError('REVISION_INPUT_PACK_CONFLICT')
    review_ref=request['review'];review_path=resolve_file(request_path.parent,review_ref['path'])
    source(review_path,review_ref['sha256']);review=read(review_path)
    if review.get('artifact_scene_sha256')!=sha(scene_path) or not review.get('reviewer'):raise GateError('REVIEW_ARTIFACT_BINDING_REQUIRED')
    findings={r['id']:r for r in review['findings']}
    if len(findings)!=len(review['findings']) or not findings:raise GateError('REVIEW_FINDINGS_REQUIRED')
    parent_record=read(base/'修订记录.json') if (base/'修订记录.json').is_file() else None
    budget=request.get('max_rounds',parent_record.get('max_rounds') if parent_record else None)
    rounds=parent_record['completed_rounds'] if parent_record else 0
    if budget is not None and (type(budget) is not int or budget<1):raise GateError('REVISION_BUDGET_INVALID')
    if budget is not None and rounds>=budget:raise GateError('REVISION_BUDGET_EXHAUSTED')
    changes=request['changes'];ids={row['object_id'] for row in changes}
    if len(ids)!=len(changes):raise GateError('REVISION_DUPLICATE_TARGET_CONFLICT')
    if not changes or ids!=set(request['allowed_object_ids']):raise GateError('REVISION_SCOPE_CONFLICT')
    selected=request['finding_ids']
    if not selected or not set(selected)<=set(findings):raise GateError('REVISION_FINDING_UNRESOLVED')
    permitted={key for identity in selected for key in findings[identity]['object_ids']}
    if not ids<=permitted:raise GateError('REVISION_OUTSIDE_REVIEW_SCOPE')
    plan=read(base/'ConstructionPlan.json');graph=read(scene_path);spec=read(base/'FigureSpec.json')
    original_graph=copy.deepcopy(graph);original_plan=copy.deepcopy(plan)
    from color_roles import check_roles, permit_display_color,prepare_reencoding
    color_contract=read(base/'color_roles.json') if (base/'color_roles.json').is_file() else None
    color_bindings=check_roles(color_contract,graph) if color_contract else {}
    if request.get('color_reencoding') and not color_contract:raise GateError('COLOR_ROLE_CONTRACT_REQUIRED')
    reencoding,updated_colors=prepare_reencoding(color_contract,graph,request) if color_contract else ({},None)
    color_changes=[]
    elements={'AI_'+o['id']:o for o in plan['elements']};objects={o['id']:o for k in ('objects','text_objects','arrow_objects') for o in graph[k]}
    geometry_changed=False
    before={p:sha(p) for p in dependency_paths(scene_path)}
    for index,change in enumerate(changes):
        identity=change['object_id'];fields=change['fields']
        if identity not in objects or not fields or not set(fields)<={'fill','stroke','stroke_width','font_size_px','translate_px','bbox_px','points_px','opacity','z_order'}:raise GateError('DISPLAY_ONLY_PATCH_REQUIRED')
        if len(set(fields)&{'translate_px','bbox_px','points_px'})>1:raise GateError('PATCH_AMBIGUOUS_GEOMETRY_OPERATIONS')
        element=elements.get(identity);obj=objects[identity];style=copy.deepcopy(graph['style_tokens'][obj['style_token']]);original_style=copy.deepcopy(style)
        if element is None and set(fields)&{'fill','font_size_px','bbox_px'}:raise GateError('RELATION_STYLE_OR_ROUTE_ONLY')
        for key,value in fields.items():
            if key in ('fill','stroke'):
                if value is not None and (not isinstance(value,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',value)):raise GateError('PATCH_COLOR_INVALID')
                if obj['geometry']['kind']=='TEXT' and (key!='fill' or value is None):raise GateError('TEXT_STYLE_PATCH_UNSUPPORTED')
                permission=permit_display_color(identity,key,style.get(key),value,color_bindings,review,reencoding)
                color_changes.append(dict(object_id=identity,field=key,permission=permission))
                if element is not None:element[key]=value
                style[key]=value
            elif key in ('translate_px','bbox_px','points_px'):
                _geometry_patch(obj,element,key,value);geometry_changed=True
                if element is None:
                    relation=next(r for r in plan['relations'] if r['relation_id']==obj['relation_id']);relation['points']=copy.deepcopy(obj['geometry']['data']['points'])
                    next(r for r in spec['routes'] if r['relationship_id']==obj['relation_id'])['waypoints']=copy.deepcopy(relation['points'])
            elif key=='z_order':
                if type(value) is not int:raise GateError('PATCH_Z_ORDER_INVALID')
                obj['z_order']=value
                if element is not None:element['z_order']=value
                else:next(r for r in plan['relations'] if r['relation_id']==obj['relation_id'])['z_order']=value
            else:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise GateError('PATCH_NUMBER_INVALID')
                if key=='font_size_px':
                    if not 1<=value<=300 or obj['geometry']['kind']!='TEXT':raise GateError('PATCH_FONT_INVALID')
                    element['data']['font_size']=value;obj['geometry']['data']['font_size']=value
                    obj['font_size']=value
                elif key=='opacity':
                    if not 0<value<=1:raise GateError('PATCH_OPACITY_INVALID_OR_HIDDEN_ELEMENT')
                    permissions=[r for r in review.get('presentation_permissions',[]) if r.get('object_id')==identity and 'opacity' in r.get('fields',[]) and r.get('reason')]
                    if len(permissions)!=1:raise GateError('PATCH_OPACITY_REVIEW_REQUIRED')
                    if element is not None:element['opacity']=value
                    style['opacity']=value
                else:
                    if not 0<=value<=20:raise GateError('PATCH_STROKE_INVALID')
                    if element is not None:element[key]=value
                    style[key]=value
        if element is None and style!=original_style:
            relation=next(r for r in plan['relations'] if r['relation_id']==obj['relation_id'])
            relation['style']={k:style[k] for k in ('stroke','stroke_width','opacity')}
        if style!=original_style:
            token='revision_'+str(rounds+1)+'_'+str(index)+'_'+identity
            graph['style_tokens'][token]=style;obj['style_token']=token
    if original_graph==graph and original_plan==plan:raise GateError('REVISION_NO_STRICT_PROGRESS_NO_ACTUAL_CHANGE')
    derived_group_bounds=_refresh_group_bounds(graph,plan) if geometry_changed else []
    endpoint_checks=_check_relation_endpoints(original_graph,graph,request) if geometry_changed else []
    out.mkdir(parents=True)
    # Copy only approved sidecars and their explicitly referenced files, preserving local paths.
    for p in before:
        if p.is_relative_to(base):
            rel=p.relative_to(base);target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    (out/'ConstructionPlan.json').write_text(__import__('json').dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'FigureSpec.json').write_text(__import__('json').dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8') if spec!=read(base/'FigureSpec.json') else None
    if reencoding:(out/'color_roles.json').write_text(__import__('json').dumps(updated_colors,ensure_ascii=False,indent=2),encoding='utf-8')
    target_scene=out/scene_path.name
    target_scene.write_text(__import__('json').dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
    checked=inspect_pack(target_scene)
    if any(sha(p)!=h for p,h in before.items()):raise GateError('REVISION_SOURCE_CHANGED')
    record=dict(status='DISPLAY_REVISION_PENDING_REVIEW',parent_scene=source(scene_path),
                parent_record_sha256=sha(base/'修订记录.json') if parent_record else None,
                completed_rounds=rounds+1,max_rounds=budget,finding_ids_before=sorted(findings),
                addressed_finding_ids=selected,changed_object_ids=sorted(ids),request=source(request_path),review=source(review_path),
                scientific_content_changed=False,unrelated_objects_changed=False,original_sources_unchanged=True,
                color_changes=color_changes,color_scope='AUTHORIZED_SCENE_ROLE_REENCODING' if reencoding else 'DECORATIVE_ONLY_OR_UNCHANGED_NOT_SCIENTIFIC_TRUTH_REVIEW',
                geometry_changed=geometry_changed,derived_group_bounds=derived_group_bounds,
                relation_endpoint_checks=endpoint_checks,scientific_semantics='CONTRACT_UNCHANGED_SPATIAL_CHECKS_ONLY_REVIEW_REQUIRED',
                new_findings=sorted(set(findings)-set(parent_record.get('finding_ids_before',[]))) if parent_record else [],
                rollback='Use the immutable parent; no source file was overwritten',next_review='PENDING',automatic_retry=False)
    # Parent record remains in the parent's directory; this record belongs to the new revision.
    (out/'修订记录.json').write_text(__import__('json').dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    save(out/'修订检查.json',checked);return record
