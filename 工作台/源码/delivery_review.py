"""Read saved PPTX objects against explicit goals; never infer scientific or visual acceptance."""
from paths import Path, read, sha, save
from core import GateError, source, writable
from scientific_gate import indexed, resolve_file
import re, math


def check_profile(contract, base):
    if contract.get('schema_version') != 'style-profile-0.1':
        raise GateError('STYLE_PROFILE_VERSION_UNSUPPORTED')
    if not all(contract.get(k) for k in ('profile_id', 'version', 'scope')):
        raise GateError('STYLE_PROFILE_IDENTITY_REQUIRED')
    ref = contract['source']; source(resolve_file(base, ref['path']), ref['sha256'])
    for row in contract.get('overrides', []):
        if not all(row.get(k) for k in ('rule', 'scope', 'reason', 'authorization_source')):
            raise GateError('STYLE_OVERRIDE_SCOPE_AND_AUTHORIZATION_REQUIRED')
        ref = row['authorization_source']; source(resolve_file(base, ref['path']), ref['sha256'])
    return dict(status='PROFILE_SOURCE_HASH_BOUND_NOT_STYLE_COMPLIANCE',
                profile_id=contract['profile_id'], version=contract['version'], scope=contract['scope'],
                overrides=contract.get('overrides', []), author_acceptance='NOT_INHERITED')


KINDS = {'text_equals', 'fill_equals', 'native_type', 'connector_targets', 'min_font_pt', 'effective_min_font_pt', 'edit_action'}


def check_requirements(contract, graph=None):
    if contract.get('schema_version') != 'delivery-requirements-0.1':
        raise GateError('DELIVERY_REQUIREMENTS_VERSION_UNSUPPORTED')
    rows = indexed(contract['observations'])
    if not rows:
        raise GateError('DELIVERY_OBSERVATIONS_REQUIRED')
    objects = indexed([*graph['objects'], *graph['text_objects'], *graph['arrow_objects'], *graph['groups']]) if graph else None
    for row in rows.values():
        if row.get('kind') not in KINDS or not row.get('object_id') or type(row.get('slide_index', 1)) is not int or row.get('slide_index', 1) < 1:
            raise GateError('DELIVERY_OBSERVATION_INVALID')
        if 'expected' not in row:
            raise GateError('DELIVERY_EXPECTATION_REQUIRED')
        if row['kind']=='fill_equals' and (not isinstance(row['expected'],str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',row['expected'])):
            raise GateError('DELIVERY_COLOR_INVALID')
        if row['kind']=='edit_action' and not row['expected']:
            raise GateError('DELIVERY_EDIT_ACTION_REQUIRED')
        if row['kind'] in ('min_font_pt','effective_min_font_pt') and (type(row['expected']) not in (int, float) or not 0 < row['expected'] <= 300):
            raise GateError('DELIVERY_FONT_INVALID')
        if objects is not None:
            if row['object_id'] not in objects:
                raise GateError('DELIVERY_OBJECT_UNRESOLVED')
            obj = objects[row['object_id']]
            if row['kind'] == 'text_equals' and row['expected'] != obj.get('geometry', {}).get('data', {}).get('text'):
                raise GateError('DELIVERY_TEXT_EXPECTATION_DIFFERS_FROM_APPROVED_SCENE')
            if row['kind']=='fill_equals' and row['expected'].upper()!=(graph['style_tokens'].get(obj.get('style_token'),{}).get('fill') or '').upper():
                raise GateError('DELIVERY_COLOR_EXPECTATION_DIFFERS_FROM_APPROVED_SCENE')
    return list(rows.values())


def verify_delivery(contract_path, artifact, out=None):
    from pptx import Presentation
    from pptx.oxml.ns import qn
    contract_path, artifact = Path(contract_path).resolve(), Path(artifact).resolve()
    contract = read(contract_path); rows = check_requirements(contract)
    bound_artifact = source(artifact); contract_ref = source(contract_path)
    prs = Presentation(str(artifact)); pages = []
    from delivery_geometry import presentation_geometry
    geometry= presentation_geometry(prs)
    def walk(shapes):
        for s in shapes:
            yield s
            if s.shape_type == 6:
                yield from walk(s.shapes)
    for slide in prs.slides:
        objects = {}
        for s in walk(slide.shapes):
            objects.setdefault(s.name, []).append(s)
        pages.append(objects)
    findings = []
    for row in rows:
        page = row.get('slide_index', 1); kind = row['kind']
        matches = pages[page-1].get(row['object_id'], []) if page <= len(pages) else []
        observed = None; state = 'FAIL'
        if len(matches) == 1:
            s = matches[0]
            if kind == 'edit_action':
                state = 'PENDING_NATIVE_EDIT_TEST'
            elif kind == 'text_equals':
                observed = s.text if s.has_text_frame else None
            elif kind == 'fill_equals':
                try: observed = '#' + str(s.fill.fore_color.rgb)
                except (AttributeError, TypeError, ValueError): pass
            elif kind == 'native_type':
                observed = ('picture' if s.shape_type == 13 else 'group' if s.shape_type == 6 else
                    'table' if s.has_table else 'connector' if s._element.tag == qn('p:cxnSp') else
                    'text' if s.has_text_frame and s.text else 'geometry')
            elif kind == 'connector_targets':
                endpoints = []
                by_id = {v.shape_id: v.name for values in pages[page-1].values() for v in values}
                for tag in ('stCxn', 'endCxn'):
                    nodes = s._element.findall('.//' + qn('a:' + tag))
                    endpoints.append(by_id.get(int(nodes[0].get('id'))) if len(nodes) == 1 else None)
                observed = dict(begin=endpoints[0], end=endpoints[1])
            elif kind in ('min_font_pt','effective_min_font_pt'):
                metrics=next((g for g in geometry[page-1] if g['native_id']==s.shape_id),{})
                sizes=[r['effective_pt' if kind=='effective_min_font_pt' else 'working_pt'] for r in metrics.get('fonts',[])]
                if sizes and all(v is not None for v in sizes):
                    observed = min(sizes); state = 'PASS' if observed >= row['expected'] else 'FAIL'
                    if kind=='effective_min_font_pt' and metrics.get('anisotropic_group'):
                        state='PENDING_ANISOTROPIC_TEXT_RENDER'
                else:
                    state = 'PENDING_NATIVE_FONT_CALIBRATION' if kind=='effective_min_font_pt' and any(r.get('size_evidence')=='NATIVE_CALIBRATION_REQUIRED' for r in metrics.get('fonts',[])) else 'PENDING_INHERITED_FONT_READBACK'
            if kind not in ('edit_action', 'min_font_pt','effective_min_font_pt'):
                expected = row['expected']
                state = 'PASS' if (observed.upper()==expected.upper() if kind=='fill_equals' and observed else observed==expected) else 'FAIL'
        findings.append(dict(id=row['id'], object_id=row['object_id'], slide_index=page, kind=kind,
            status=state, expected=row.get('expected'), observed=observed, matching_objects=len(matches)))
    source(artifact, bound_artifact['sha256']); source(contract_path, contract_ref['sha256'])
    result = dict(status='FAIL' if any(r['status']=='FAIL' for r in findings) else
        'PENDING_NATIVE_CHECKS' if any(r['status']!='PASS' for r in findings) else 'PASS_SAVED_OBJECT_SCOPE_ONLY',
        artifact=bound_artifact, requirements=contract_ref, observations=findings,
        native_application_reopen='NOT_PERFORMED', visual='PENDING', scientific_truth='NOT_ASSESSED', author_acceptance='PENDING')
    if out is not None:
        out = writable(out)
        if out.exists(): raise FileExistsError(out)
        save(out/'最终对象核对.json', result)
    return result


def audit_presentation(artifact, profile=None, out=None):
    """Screen the actual saved deck. Frame overlap is a review candidate, not glyph proof.

    The optional profile is task/author-specific. No universal family, font count,
    integer size, minimum size, or paper width is imposed by this function.
    """
    from pptx import Presentation
    from delivery_geometry import presentation_geometry
    artifact=Path(artifact).resolve();bound=source(artifact);profile=profile or {}
    for key in ('minimum_effective_font_pt','maximum_body_size_levels','target_width_mm'):
        if key in profile and (type(profile[key]) not in (int,float) or not math.isfinite(profile[key]) or profile[key]<=0):
            raise GateError('DELIVERY_PROFILE_VALUE_INVALID: '+key)
    prs=Presentation(str(artifact));pages=presentation_geometry(prs);findings=[]
    output_scale=profile.get('target_width_mm',prs.slide_width/36000)/(prs.slide_width/36000)
    allowed={frozenset(v['object_ids']) for v in profile.get('intentional_overlaps',[]) if v.get('reason')}
    for index,objects in enumerate(pages,1):
        levels=set()
        for obj in objects:
            for run in obj['fonts']:
                if run['effective_pt'] is not None:run['effective_pt']*=output_scale
                run['whole_page_scale']=output_scale
                if run['geometric_estimate_pt'] is not None:run['geometric_estimate_at_target_pt']=run['geometric_estimate_pt']*output_scale
                if run.get('size_evidence')=='NATIVE_CALIBRATION_REQUIRED':
                    findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='font_size_requires_native_calibration',
                        geometric_estimate_pt=run['geometric_estimate_at_target_pt'],status='REVIEW_REQUIRED'))
                if run['working_pt'] is not None and not run['baseline']:levels.add(round(run['working_pt'],4))
                if run['working_pt'] is None:
                    findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='unresolved_font',status='REVIEW_REQUIRED'))
                elif profile.get('integer_working_sizes') and not run['baseline'] and abs(run['working_pt']-round(run['working_pt']))>1e-6:
                    findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='noninteger_working_font',working_pt=run['working_pt'],status='FAIL_PROFILE'))
                if run['effective_pt'] is not None and 'minimum_effective_font_pt' in profile and run['effective_pt']<profile['minimum_effective_font_pt']:
                    findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='small_effective_font',effective_pt=run['effective_pt'],status='FAIL_PROFILE' if not obj['anisotropic_group'] else 'REVIEW_REQUIRED'))
                if profile.get('required_font_family'):
                    family=run['font_family_declaration']
                    if family is None:
                        findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='font_family_inheritance_requires_review',status='REVIEW_REQUIRED'))
                    elif family.casefold()!=profile['required_font_family'].casefold():
                        findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='font_family_conflict',observed=family,status='FAIL_PROFILE'))
            if obj['fonts'] and obj['anisotropic_group']:
                findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='anisotropic_group_text',status='REVIEW_REQUIRED'))
            a=obj['bbox_pt']
            if min(a[:2])<-.01 or a[2]>prs.slide_width/12700+.01 or a[3]>prs.slide_height/12700+.01:
                findings.append(dict(slide_index=index,object_ids=[obj['object_id']],kind='outside_slide',bbox_pt=a,status='REVIEW_REQUIRED'))
            if not obj['text']:continue
            for other in objects[obj['z_order']+1:]:
                pair=[obj['object_id'],other['object_id']]
                if frozenset(pair) in allowed or not other['cover_kind']:continue
                b=other['bbox_pt'];iw=min(a[2],b[2])-max(a[0],b[0]);ih=min(a[3],b[3])-max(a[1],b[1])
                if iw>0 and ih>0:
                    findings.append(dict(slide_index=index,object_ids=pair,kind='text_covered_by_later_object_candidate',
                        overlap_fraction_of_text_frame=iw*ih/max((a[2]-a[0])*(a[3]-a[1]),1e-12),
                        cover_kind=other['cover_kind'],status='REVIEW_REQUIRED'))
        if profile.get('maximum_body_size_levels') and len(levels)>profile['maximum_body_size_levels']:
            findings.append(dict(slide_index=index,object_ids=[],kind='too_many_working_font_levels',sizes_pt=sorted(levels),status='FAIL_PROFILE'))
    source(artifact,bound['sha256'])
    report=dict(status='FAIL_PROFILE' if any(f['status']=='FAIL_PROFILE' for f in findings) else 'REVIEW_REQUIRED' if findings else 'NO_AUTOMATIC_FINDINGS',
        artifact=bound,profile=profile,physical_page_mm=[prs.slide_width/36000,prs.slide_height/36000],output_scale=output_scale,
        pages=pages,findings=findings,scope='Saved object transforms, common font inheritance and z-order; frame overlap is only a candidate.',
        rendered_text_bounds='NOT_MEASURED',native_reopen='NOT_PERFORMED',visual='PENDING',scientific_truth='NOT_ASSESSED',author_acceptance='PENDING')
    if out is not None:
        out=writable(out)
        if out.exists():raise FileExistsError(out)
        save(out/'版面与有效字号核对.json',report)
    return report
