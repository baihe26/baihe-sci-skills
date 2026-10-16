"""Apply a reviewed, display-only patch into a new immutable revision."""
from paths import Path,read,save,sha
from core import writable,GateError,source
from preflight import inspect_pack
from scientific_gate import resolve_file
from pack_files import dependency_paths
import copy,shutil,re,math

def revise(scene_path,request_path,out):
    scene_path=Path(scene_path).resolve();request_path=Path(request_path).resolve();out=writable(out);base=scene_path.parent
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
    budget=parent_record['max_rounds'] if parent_record else request.get('max_rounds',2)
    rounds=parent_record['completed_rounds'] if parent_record else 0
    if type(budget) is not int or not 1<=budget<=5:raise GateError('REVISION_BUDGET_INVALID')
    if rounds>=budget:raise GateError('REVISION_BUDGET_EXHAUSTED')
    if parent_record and not set(findings)<set(parent_record['finding_ids_before']):raise GateError('REVISION_NO_STRICT_PROGRESS')
    changes=request['changes'];ids={row['object_id'] for row in changes}
    if len(ids)!=len(changes):raise GateError('REVISION_DUPLICATE_TARGET_CONFLICT')
    if not changes or ids!=set(request['allowed_object_ids']):raise GateError('REVISION_SCOPE_CONFLICT')
    selected=request['finding_ids']
    if not selected or not set(selected)<=set(findings):raise GateError('REVISION_FINDING_UNRESOLVED')
    permitted={key for identity in selected for key in findings[identity]['object_ids']}
    if not ids<=permitted:raise GateError('REVISION_OUTSIDE_REVIEW_SCOPE')
    plan=read(base/'ConstructionPlan.json');graph=read(scene_path)
    elements={'AI_'+o['id']:o for o in plan['elements']};objects={o['id']:o for k in ('objects','text_objects') for o in graph[k]}
    before={p:sha(p) for p in dependency_paths(scene_path)}
    for index,change in enumerate(changes):
        identity=change['object_id'];fields=change['fields']
        if identity not in elements or identity not in objects or not fields or not set(fields)<={'fill','stroke','stroke_width','font_size_px'}:raise GateError('DISPLAY_ONLY_PATCH_REQUIRED')
        element=elements[identity];obj=objects[identity];style=copy.deepcopy(graph['style_tokens'][obj['style_token']])
        for key,value in fields.items():
            if key in ('fill','stroke'):
                if value is not None and (not isinstance(value,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',value)):raise GateError('PATCH_COLOR_INVALID')
                if obj['geometry']['kind']=='TEXT' and (key!='fill' or value is None):raise GateError('TEXT_STYLE_PATCH_UNSUPPORTED')
                element[key]=value;style[key]=value
            else:
                if not isinstance(value,(int,float)) or not math.isfinite(value):raise GateError('PATCH_NUMBER_INVALID')
                if key=='font_size_px':
                    if not 1<=value<=300 or obj['geometry']['kind']!='TEXT':raise GateError('PATCH_FONT_INVALID')
                    element['data']['font_size']=value;obj['geometry']['data']['font_size']=value
                else:
                    if not 0<=value<=20:raise GateError('PATCH_STROKE_INVALID')
                    element[key]=value;style[key]=value
        token='revision_'+str(rounds+1)+'_'+str(index)+'_'+identity
        graph['style_tokens'][token]=style;obj['style_token']=token
    out.mkdir(parents=True)
    # Copy only approved sidecars and their explicitly referenced files, preserving local paths.
    for p in before:
        if p.is_relative_to(base):
            rel=p.relative_to(base);target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    (out/'ConstructionPlan.json').write_text(__import__('json').dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    target_scene=out/scene_path.name
    target_scene.write_text(__import__('json').dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
    checked=inspect_pack(target_scene)
    if any(sha(p)!=h for p,h in before.items()):raise GateError('REVISION_SOURCE_CHANGED')
    record=dict(status='DISPLAY_REVISION_PENDING_REVIEW',parent_scene=source(scene_path),
                parent_record_sha256=sha(base/'修订记录.json') if parent_record else None,
                completed_rounds=rounds+1,max_rounds=budget,finding_ids_before=sorted(findings),
                addressed_finding_ids=selected,changed_object_ids=sorted(ids),request=source(request_path),review=source(review_path),
                scientific_content_changed=False,unrelated_objects_changed=False,original_sources_unchanged=True,
                rollback='Use the immutable parent; no source file was overwritten',next_review='PENDING',automatic_retry=False)
    # Parent record remains in the parent's directory; this record belongs to the new revision.
    (out/'修订记录.json').write_text(__import__('json').dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    save(out/'修订检查.json',checked);return record
