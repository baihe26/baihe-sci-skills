"""Optional semantic colour bindings; legacy packs remain readable, never silently recoloured."""
from core import GateError
from scientific_gate import indexed
import re


def check_roles(contract, graph):
    if contract.get('schema_version') != 'color-roles-0.1':
        raise GateError('COLOR_ROLE_VERSION_UNSUPPORTED')
    objects = indexed([*graph['objects'], *graph['text_objects'], *graph['arrow_objects']])
    bindings = {}
    for row in contract['bindings']:
        key = (row['object_id'], row['field'])
        if key in bindings or key[0] not in objects or key[1] not in ('fill', 'stroke'):
            raise GateError('COLOR_ROLE_TARGET_INVALID')
        if row.get('kind') not in ('decorative', 'scientific') or not row.get('reason'):
            raise GateError('COLOR_ROLE_CLASSIFICATION_REQUIRED')
        if row['kind'] == 'scientific':
            color = row.get('value')
            if not row.get('role') or not isinstance(color, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', color):
                raise GateError('SCIENTIFIC_COLOR_BINDING_REQUIRED')
            targets = [key[0], *row.get('legend_object_ids', [])]
            for identity in targets:
                if identity not in objects:
                    raise GateError('COLOR_LEGEND_UNRESOLVED')
                style = graph['style_tokens'][objects[identity]['style_token']]
                if (style.get(key[1]) or '').upper() != color.upper():
                    raise GateError('SCIENTIFIC_COLOR_ROLE_CONFLICT: ' + identity)
        bindings[key] = row
    return bindings


def permit_display_color(identity, field, old, new, bindings, review, reencoding=None):
    if old == new or isinstance(old,str) and isinstance(new,str) and old.upper()==new.upper():
        return 'UNCHANGED'
    if (identity,field) in (reencoding or {}) and isinstance(new,str) and new.upper()==reencoding[(identity,field)].upper():
        return 'AUTHORIZED_CONSISTENT_REENCODING'
    binding = bindings.get((identity, field))
    if binding:
        if binding['kind'] == 'scientific':
            if (identity,field) in (reencoding or {}):
                approved=reencoding[(identity,field)]
                if isinstance(new,str) and new.upper()==approved.upper():return 'AUTHORIZED_CONSISTENT_REENCODING'
            raise GateError('SCIENTIFIC_COLOR_REENCODING_REQUIRES_NEW_APPROVED_DESIGN')
        return 'DECLARED_DECORATIVE'
    # Hash-bound review can scope a legacy decorative change. A generic object
    # finding alone is insufficient evidence that colour has no scientific meaning.
    permissions = review.get('decorative_color_permissions', [])
    matches = [r for r in permissions if r.get('object_id') == identity and field in r.get('fields', []) and r.get('reason')]
    if len(matches) != 1:
        raise GateError('COLOR_MEANING_UNKNOWN_EXPLICIT_DECORATIVE_REVIEW_REQUIRED: ' + identity)
    return 'REVIEWED_DECORATIVE'


def prepare_reencoding(contract, graph, request):
    """Reencode an explicitly authorized role and every bound legend together.

    Does not infer identity from colour and does not recolour microscopy channels.
    Cross-figure consistency remains a delivery-scope check, never claimed here.
    """
    import copy
    bindings=check_roles(contract,graph)
    changed={(row['object_id'],key):value for row in request.get('changes',[]) for key,value in row.get('fields',{}).items()}
    permitted={};updated=copy.deepcopy(contract);seen=set()
    for rule in request.get('color_reencoding',[]):
        role=rule.get('role')
        if not role or role in seen or rule.get('scope')!='current_scene' or not rule.get('authorization'):
            raise GateError('COLOR_REENCODING_AUTHORIZATION_REQUIRED')
        seen.add(role);rows=[r for r in updated['bindings'] if r.get('kind')=='scientific' and r.get('role')==role]
        if not rows:raise GateError('COLOR_REENCODING_ROLE_MISSING')
        new=rule.get('to')
        if not isinstance(new,str) or not re.fullmatch('#[0-9a-fA-F]{6}',new):raise GateError('COLOR_REENCODING_VALUE_INVALID')
        for row in rows:
            if row.get('protected_channel') or row.get('encoding_domain') in ('microscopy_channel','measured_pseudocolor'):
                raise GateError('MEASUREMENT_CHANNEL_REENCODING_NOT_DISPLAY_ONLY')
            if (rule.get('from') or '').upper()!=row['value'].upper():raise GateError('COLOR_REENCODING_PARENT_CONFLICT')
            for identity in [row['object_id'],*row.get('legend_object_ids',[])]:
                key=(identity,row['field']);target=(changed.get(key) or '')
                if not isinstance(target,str) or target.upper()!=new.upper():raise GateError('COLOR_REENCODING_INCOMPLETE_LEGEND_OR_OBJECT: '+identity)
                permitted[key]=new
            row['value']=new
    return permitted,updated
