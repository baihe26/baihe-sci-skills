"""Versioned presentation extensions around the unchanged frozen scene schema."""
import copy
import math
import re
from core import GateError


def number(value, name, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GateError('STYLE_NUMBER_INVALID: ' + name)
    if low is not None and value < low or high is not None and value > high:
        raise GateError('STYLE_NUMBER_RANGE: ' + name)
    return value


def gradient(value):
    if not isinstance(value, dict) or set(value) - {'kind', 'angle_deg', 'center', 'stops'}:
        raise GateError('GRADIENT_FIELDS_INVALID')
    kind = value.get('kind')
    if kind not in ('linear', 'radial'):
        raise GateError('GRADIENT_KIND_INVALID')
    if kind == 'linear':
        number(value.get('angle_deg', 0), 'angle_deg')
        if 'center' in value:
            raise GateError('LINEAR_GRADIENT_HAS_RADIAL_CENTER')
    else:
        if 'angle_deg' in value:
            raise GateError('RADIAL_GRADIENT_HAS_LINEAR_ANGLE')
        center = value.get('center', [.5, .5])
        if not isinstance(center, list) or len(center) != 2:
            raise GateError('GRADIENT_CENTER_INVALID')
        for v in center:
            number(v, 'center', 0, 1)
    stops = value.get('stops', [])
    if not isinstance(stops, list) or len(stops) < 2:
        raise GateError('GRADIENT_STOPS_REQUIRED')
    previous = -1
    for stop in stops:
        if not isinstance(stop, dict) or set(stop) - {'offset', 'color', 'opacity'}:
            raise GateError('GRADIENT_STOP_INVALID')
        offset = number(stop.get('offset'), 'offset', 0, 1)
        if offset <= previous:
            raise GateError('GRADIENT_STOP_ORDER_INVALID')
        previous = offset
        if not isinstance(stop.get('color'), str) or not re.fullmatch('#[0-9a-fA-F]{6}', stop['color']):
            raise GateError('GRADIENT_COLOR_INVALID')
        number(stop.get('opacity', 1), 'stop.opacity', 0, 1)
    if stops[0]['offset'] != 0 or stops[-1]['offset'] != 1:
        raise GateError('GRADIENT_ENDPOINT_STOPS_REQUIRED')
    return value


def validate_style(style):
    number(style.get('opacity', 1), 'opacity', 0, 1)
    if 'fill_gradient' in style:
        gradient(style['fill_gradient'])
    return style


def schema_projection(graph):
    """Validate extension values, then remove only known extension for old schema.

    Unknown fields still reach the frozen schema and fail normally.
    """
    clone = copy.deepcopy(graph)
    for style in clone['style_tokens'].values():
        validate_style(style)
        style.pop('fill_gradient', None)
    return clone


def apply_plan_styles(plan, graph):
    """The old compiler hardcodes opacity/relations; restore declared presentation."""
    elements = {'AI_' + e['id']: e for e in plan['elements']}
    relations = {r['relation_id']: r for r in plan['relations']}
    for obj in [*graph['objects'], *graph['text_objects'], *graph['arrow_objects']]:
        source = relations[obj['relation_id']].get('style', {}) if 'relation_id' in obj else elements[obj['id']]
        planned=relations[obj['relation_id']] if 'relation_id' in obj else elements[obj['id']]
        if 'z_order' in planned:
            if type(planned['z_order']) is not int:raise GateError('STYLE_Z_ORDER_INVALID')
            obj['z_order']=planned['z_order']
        if 'relation_id' in obj:
            relation=relations[obj['relation_id']]
            # The approved encoding, not the epistemic label alone, controls the
            # line. validate_design has already checked the actual disclosure.
            obj['geometry']['data']['dash']='6 5' if relation['encoding']=='dashed_arrow' else None
        additions = {k: source[k] for k in ('opacity', 'fill_gradient') if k in source}
        if 'relation_id' in obj:
            additions.update({k: source[k] for k in ('stroke', 'stroke_width') if k in source})
        if additions:
            style = copy.deepcopy(graph['style_tokens'][obj['style_token']])
            style.update(additions)
            validate_style(style)
            token = obj['style_token'] + '_display_' + obj['id']
            graph['style_tokens'][token] = style
            obj['style_token'] = token
    return graph


def capability_route(graph, requested='portable', retained_assets=False):
    """Read-only route selection; a handoff is not native production."""
    requirements = set()
    kinds = {o['geometry']['kind'] for k in ('objects', 'text_objects', 'arrow_objects') for o in graph[k]}
    if 'PATH' in kinds:
        from vector_paths import path_commands
        try:
            for o in graph['objects']:
                if o['geometry']['kind']=='PATH':path_commands(o['geometry']['data'].get('d'))
            requirements.add('editable_bezier_path')
        except GateError:requirements.add('svg_path')
    if kinds - {'RECT', 'ELLIPSE', 'POLYLINE', 'TEXT', 'PATH'}: requirements.add('custom_geometry')
    if graph.get('asset_refs') or graph.get('clipping'): requirements.add('scene_assets_or_clip')
    if retained_assets: requirements.add('retained_image')
    for style in graph['style_tokens'].values():
        validate_style(style)
        if style.get('opacity', 1) != 1: requirements.add('opacity')
        if 'fill_gradient' in style: requirements.add(style['fill_gradient']['kind'] + '_gradient')
    capabilities = {
        'portable': {'opacity', 'linear_gradient', 'radial_gradient', 'retained_image', 'editable_bezier_path'},
        'illustrator': {'opacity', 'linear_gradient', 'radial_gradient', 'svg_path', 'editable_bezier_path'},
        'ppt_native': {'opacity'},
    }
    if requested not in capabilities: raise GateError('UNKNOWN_VECTOR_BACKEND')
    missing = requirements - capabilities[requested]
    alternatives = [key for key, supported in capabilities.items() if requirements <= supported]
    return dict(status='SUPPORTED_BY_ADAPTER_PENDING_NATIVE_REVIEW' if not missing else 'EXPLICIT_HANDOFF_REQUIRED',
                requested=requested, requirements=sorted(requirements), unsupported=sorted(missing),
                alternatives=alternatives, automatic_flattening=False,
                next_action=('按当前后端另存并检查实际成品。' if not missing else
                             '选择 alternatives 中的现有后端；若为空，保留当前原生父本，在原生编辑路线完成这些效果，不能简化或栅格化冒充完成。'))
