"""Cross-artifact identity checks. Consistency is separate from scientific truth."""
from paths import read, sha, digest, Path
from core import GateError
import math


def fail(code, detail):
    raise GateError(code + ': ' + str(detail))


def indexed(rows, key='id'):
    result = {}
    for row in rows:
        identity = row.get(key)
        if not identity or identity in result:
            fail('MISSING_OR_DUPLICATE_ID', identity)
        result[identity] = row
    return result


def same(left, right, code):
    if left != right:
        fail(code, dict(expected=left, observed=right))


def resolve_file(base, ref):
    p = Path(ref)
    return p.resolve() if p.is_absolute() else (Path(base) / p).resolve()


def validate_design(spec, plan, binding, spec_base, binding_base):
    """Run before creating previews or native output; never repair a contradiction."""
    meta = spec['metadata']
    source = binding.get('source_file', {})
    if not source.get('path') or not source.get('sha256'):
        fail('SOURCE_BINDING_REQUIRED', source)
    p = resolve_file(binding_base, source['path'])
    if not p.is_file():
        fail('SOURCE_MISSING', p)
    same(source['sha256'], sha(p), 'SOURCE_HASH_CONFLICT')
    same(meta['input_sha256'], sha(p), 'INPUT_HASH_CONFLICT')
    # A single file-final newline is administrative; internal whitespace is evidence.
    actual_text = p.read_text(encoding='utf-8-sig')
    if actual_text != meta['input_text'] and actual_text.removesuffix('\n') != meta['input_text']:
        fail('INPUT_TEXT_CONFLICT', 'input_text differs from the bound UTF-8 source')
    sources = indexed(meta['sources'])
    for item in sources.values():
        q = resolve_file(spec_base, item['path'])
        if not q.is_file():
            fail('SOURCE_MISSING', q)
        same(item['sha256'], sha(q), 'SOURCE_HASH_CONFLICT')
    entities = indexed(spec['entities'])
    claims = indexed(spec['scientific_claims'])
    bound_claims = indexed(binding.get('claims', []))
    same(set(claims), set(bound_claims), 'BINDING_CLAIM_SET_CONFLICT')
    for identity, c in claims.items():
        same(c, bound_claims[identity], 'BINDING_CLAIM_CONFLICT')
        span = c['source_span']
        if not 0 <= span['start'] < span['end'] <= len(meta['input_text']):
            fail('SOURCE_SPAN_INVALID', identity)
        same(span['quote'], meta['input_text'][span['start']:span['end']], 'SOURCE_SPAN_MISMATCH')
        if not set(c['entity_ids']) <= set(entities):
            fail('CLAIM_ENTITY_UNRESOLVED', identity)
        if not set(c['supporting_source_ids']) <= set(sources):
            fail('CLAIM_SOURCE_UNRESOLVED', identity)
    instances = indexed(plan['instances'])
    same(set(entities), set(instances), 'PLAN_ENTITY_SET_CONFLICT')
    for identity, e in entities.items():
        # The frozen format explicitly uses scientific_role for instance.entity_id.
        same(e['scientific_role'], instances[identity]['entity_id'], 'PLAN_ENTITY_MAPPING_CONFLICT')
        for span in e.get('source_spans', []):
            same(span['quote'], meta['input_text'][span['start']:span['end']], 'ENTITY_SPAN_MISMATCH')
    relations = indexed(spec['relationships'])
    bound_relations = indexed(binding.get('relations', []))
    planned = indexed(plan['relations'], 'relation_id')
    routes = indexed(spec['routes'], 'relationship_id')
    for rows in (bound_relations, planned, routes):
        same(set(relations), set(rows), 'RELATION_SET_CONFLICT')
    for identity, r in relations.items():
        b, q, route = bound_relations[identity], planned[identity], routes[identity]
        for key in ('source', 'target', 'relation_type', 'direction', 'certainty', 'visual_encoding', 'claim_id'):
            same(r[key], b.get(key), 'BINDING_RELATION_CONFLICT/' + key)
        same(r.get('negated', False), b.get('negated', False), 'BINDING_NEGATION_CONFLICT')
        if r['source'] not in entities or r['target'] not in entities or r['claim_id'] not in claims:
            fail('RELATION_ID_UNRESOLVED', identity)
        same(r['certainty'], claims[r['claim_id']]['evidence_level'], 'CLAIM_RELATION_CERTAINTY_CONFLICT')
        if r['certainty'] in ('HYPOTHESIZED', 'INFERRED') and r['visual_encoding'] in ('solid_arrow', 'inhibition_bar'):
            fail('HYPOTHESIS_UPGRADED', identity)
        for key, target in (('source', 'source'), ('target', 'target'), ('relation_type', 'predicate'),
                            ('certainty', 'epistemic_status'), ('visual_encoding', 'encoding')):
            same(r[key], q.get(target), 'PLAN_RELATION_CONFLICT/' + key)
        same([r['claim_id']], q.get('claim_ids'), 'PLAN_CLAIM_CONFLICT')
        same(r.get('negated', False), q.get('negated', False), 'PLAN_NEGATION_CONFLICT')
        same(r['visual_encoding'], route['encoding'], 'ROUTE_ENCODING_CONFLICT')
        same(route['waypoints'], q['points'], 'ROUTE_POINTS_CONFLICT')
    known_refs = set(entities) | {e['scientific_role'] for e in entities.values()} | set(claims) | set(relations)
    indexed(plan['elements'])
    for element in plan['elements']:
        if element.get('owner') is not None and element['owner'] not in entities:
            fail('ELEMENT_OWNER_UNRESOLVED', element['id'])
        if not set(element.get('scientific_refs', [])) <= known_refs:
            fail('ELEMENT_SCIENTIFIC_REF_UNRESOLVED', element['id'])
    return dict(status='PASS', scientific_truth='NOT_ASSESSED', claims=len(claims), relations=len(relations),
                source_sha256=sha(p), contract_sha256=digest(dict(spec=spec, plan=plan, binding=binding)))


def validate_scene(spec, plan, graph):
    """Check frozen compiler output against the explicit plan ID mapping."""
    entities = indexed(spec['entities'])
    same(plan['canvas'],[graph['canvas']['width'],graph['canvas']['height']],'SCENE_CANVAS_CONFLICT')
    same(('px','TOP_LEFT'),(graph['canvas']['unit'],graph['canvas']['origin']),'SCENE_COORDINATE_CONFLICT')
    scale=graph['geometry']['coordinate_transform']['scale_pt_per_px']
    expected_scale=spec['style']['canvas_width_mm']/graph['canvas']['width']*72/25.4
    if not isinstance(scale,(int,float)) or not math.isfinite(scale) or abs(scale-expected_scale)>1e-10:
        fail('SCENE_PHYSICAL_SCALE_CONFLICT',scale)
    groups = indexed(graph['groups'])
    all_objects=indexed([*graph['objects'],*graph['text_objects'],*graph['arrow_objects'],*graph['groups']])
    parents={}
    for link in graph['parent_child']:
        child,parent=link['child_id'],link['parent_id']
        if child not in all_objects or parent not in groups or child in parents:fail('SCENE_PARENT_UNRESOLVED_OR_DUPLICATE',link)
        parents[child]=parent
    for key in all_objects:
        trail=set();current=key
        while current in parents:
            if current in trail:fail('SCENE_PARENT_CYCLE',key)
            trail.add(current);current=parents[current]
    for row in [*graph['objects'],*graph['text_objects'],*graph['arrow_objects']]:
        same(row.get('group_id'),parents.get(row['id']),'SCENE_PARENT_DECLARATION_CONFLICT')
    mapping = {}
    for identity, e in entities.items():
        expected_name = 'AI_' + e['scientific_role'] + '__' + identity
        matches = [g['id'] for g in groups.values() if g.get('name') == expected_name]
        if len(matches) != 1:
            fail('SCENE_ENTITY_MAPPING_CONFLICT', identity)
        mapping[identity] = matches[0]
    primitives = indexed([*graph['objects'], *graph['text_objects']])
    expected_primitives = {'AI_' + e['id']: e for e in plan['elements']}
    same(set(expected_primitives), set(primitives), 'SCENE_ELEMENT_SET_CONFLICT')
    for identity, element in expected_primitives.items():
        native = primitives[identity]
        same(element['kind'], native['geometry']['kind'], 'SCENE_ELEMENT_KIND_CONFLICT')
        style = graph['style_tokens'][native['style_token']]
        for field in ('fill', 'stroke'):
            # The frozen compiler intentionally emits TEXT as live glyph fill,
            # ignoring its plan stroke. Preserve that established representation.
            if field == 'stroke' and element['kind'] == 'TEXT':
                continue
            same(element.get(field), style.get(field), 'SCENE_ELEMENT_STYLE_CONFLICT/' + field)
        expected_data = dict(element['data'], dash=element.get('dash'))
        same(expected_data, native['geometry']['data'], 'SCENE_ELEMENT_CONTENT_CONFLICT')
        same(element['scientific_refs'], native['scientific_refs'], 'SCENE_ELEMENT_REF_CONFLICT')
        same(mapping[element['owner']] if element.get('owner') else None, native['group_id'], 'SCENE_ELEMENT_OWNER_CONFLICT')
    arrows = indexed(graph['arrow_objects'], 'relation_id')
    same(set(arrows), {r['id'] for r in spec['relationships']}, 'SCENE_RELATION_SET_CONFLICT')
    planned = indexed(plan['relations'], 'relation_id')
    for r in spec['relationships']:
        a = arrows[r['id']]
        for expected, observed in ((mapping[r['source']], a['source_id']), (mapping[r['target']], a['target_id']),
                                    (r['certainty'], a['epistemic_status']), (r['relation_type'], a['arrow_semantics']),
                                    (r.get('negated', False), a.get('negated', False)),
                                    (r['visual_encoding'], a['geometry']['data']['encoding']),
                                    (planned[r['id']]['points'], a['geometry']['data']['points'])):
            same(expected, observed, 'SCENE_RELATION_CONFLICT')
        if not {r['id'], r['claim_id']} <= set(a['scientific_refs']):
            fail('SCENE_CLAIM_CONFLICT', r['id'])
    return dict(status='PASS', entity_to_scene=mapping, scientific_truth='NOT_ASSESSED')


def validate_pack(scene_path):
    folder = Path(scene_path).parent
    required = ['FigureSpec.json', 'ConstructionPlan.json', 'scientific_binding.json']
    if any(not (folder / name).is_file() for name in required):
        fail('SCIENTIFIC_SIDECARS_REQUIRED', required)
    spec, plan, binding = (read(folder / name) for name in required)
    return dict(design=validate_design(spec, plan, binding, folder, folder),
                scene=validate_scene(spec, plan, read(scene_path)))
