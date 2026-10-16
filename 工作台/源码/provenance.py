"""An auditable source -> claim -> scene object -> saved occurrence chain.

Entity membership is contextual, not evidence that every entity proves a claim.
The contract carries declared evidence; it never upgrades its scientific status.
"""
from paths import Path, read, save, sha, digest
from core import GateError, source
from scientific_gate import indexed


def scene_trace(scene_path, inspection=None):
    from preflight import inspect_pack
    scene_path = Path(scene_path).resolve()
    inspection = inspection or inspect_pack(scene_path)
    if inspection['scene_sha256'] != sha(scene_path):
        raise GateError('TRACE_SCENE_CHANGED')
    base = scene_path.parent
    graph, spec = read(scene_path), read(base / 'FigureSpec.json')
    evidence_map = read(base / 'evidence_map.json') if (base / 'evidence_map.json').is_file() else {}
    mapped = indexed(evidence_map.get('claims', []))
    claims = indexed(spec['scientific_claims'])
    entities = indexed(spec['entities'])
    roles = {row['scientific_role']: key for key, row in entities.items()}
    relations = indexed(spec['relationships'])
    links = []
    for key in ('objects', 'arrow_objects', 'text_objects', 'groups'):
        for obj in graph[key]:
            refs = obj.get('scientific_refs', [])
            direct, contextual = set(), set()
            for ref in refs:
                if ref in claims:
                    direct.add(ref)
                elif ref in relations:
                    direct.add(relations[ref]['claim_id'])
                else:
                    entity = ref if ref in entities else roles.get(ref)
                    contextual.update(c['id'] for c in claims.values() if entity in c['entity_ids'])
            contextual -= direct
            links.append(dict(object_id=obj['id'], object_kind=key, scientific_refs=refs,
                              direct_claim_ids=sorted(direct), contextual_claim_ids=sorted(contextual),
                              mapping='EXPLICIT_BINDING_WITH_ENTITY_CONTEXT_NOT_CAUSAL_PROOF'))
    for asset in inspection['retained_assets']['assets']:
        links.append(dict(object_id=asset['id'], object_kind='retained_pixels', scientific_refs=[],
                          direct_claim_ids=[], contextual_claim_ids=[], source_sha256=asset['source_sha256'],
                          source_box_px=asset['source_box_px'], mapping='PIXEL_SOURCE_ONLY'))
    # Keep source spans and epistemic status, including limitations/contradictions.
    claim_rows = [dict(claim=c, evidence_links=mapped.get(c['id'], {}).get('links', []),
                       evidence_mapping='MAPPED' if c['id'] in mapped else 'NOT_RECORDED') for c in claims.values()]
    return dict(schema_version='provenance-contract-0.1', scene=source(scene_path),
                input_fingerprint=inspection['input_fingerprint'], binding=source(base / 'scientific_binding.json'),
                declared_sources=spec['metadata']['sources'], source_blocks=evidence_map.get('source_blocks', []),
                evidence=evidence_map.get('evidence', []), claims=claim_rows, objects=links,
                reconstruction=inspection['reconstruction'], scientific_review='PENDING', author_acceptance='PENDING',
                locator_verification='TEXT_QUOTES_CHECKED_WHEN_DECLARED_PDF_LOCATORS_NOT_INDEPENDENTLY_VERIFIED',
                automatic_adoption=False)


def object_tags(contract, identity):
    rows = {row['object_id']: row for row in contract['objects']}
    if identity not in rows:
        raise GateError('TRACE_OBJECT_UNRESOLVED: ' + identity)
    row = rows[identity]
    return dict(PROVENANCE_SHA256=digest(contract), SCENE_SHA256=contract['scene']['sha256'],
                CLAIM_IDS=','.join(row['direct_claim_ids']), CONTEXT_CLAIM_IDS=','.join(row['contextual_claim_ids']))


def record_trace(out, contract, artifact, occurrences):
    if not occurrences or len({(r['slide_id'], r['object_id']) for r in occurrences}) != len(occurrences):
        raise GateError('TRACE_OCCURRENCE_MISSING_OR_DUPLICATE')
    expected = {row['object_id'] for row in contract['objects']}
    if {r['object_id'] for r in occurrences} != expected:
        raise GateError('TRACE_NATIVE_OBJECT_SET_CONFLICT')
    result = dict(schema_version='provenance-delivery-0.1', contract=contract, contract_sha256=digest(contract),
                  artifact=source(artifact), occurrences=occurrences,
                  status='SOURCE_MAPPING_AND_NATIVE_LOCATION_RECORDED', scientific_review='PENDING', author_acceptance='PENDING')
    save(Path(out) / '来源与引用链.json', result)
    return result


def verify_trace(trace_path, artifact=None):
    """Verify the saved chain and current inputs; no visual/scientific acceptance."""
    row = read(trace_path)
    contract = row['contract']
    if digest(contract) != row['contract_sha256']:
        raise GateError('TRACE_CONTRACT_HASH_CONFLICT')
    refs=row['occurrences']
    if not refs or {r['object_id'] for r in refs}!={r['object_id'] for r in contract['objects']} or len({(r['slide_id'],r['object_id']) for r in refs})!=len(refs):
        raise GateError('TRACE_OCCURRENCE_COVERAGE_CONFLICT')
    fresh = scene_trace(contract['scene']['path'])
    if digest(fresh) != row['contract_sha256']:
        raise GateError('TRACE_INPUT_PACK_CHANGED')
    source(artifact or row['artifact']['path'], row['artifact']['sha256'])
    if Path(artifact or row['artifact']['path']).suffix.lower() == '.pptx':
        from pptx_tags import presentation_locations
        current = presentation_locations(artifact or row['artifact']['path'])
        for ref in row['occurrences']:
            matches = [q for q in current if q['slide_id'] == ref['slide_id'] and q['object_id'] == ref.get('native_object_id', ref['object_id'])]
            if len(matches) != 1 or matches[0]['native_id'] != ref['native_id'] or matches[0]['tags'].get('PROVENANCE_SHA256') != row['contract_sha256']:
                raise GateError('TRACE_NATIVE_OCCURRENCE_CONFLICT')
    return dict(status='PASS_RECORDED_MAPPING', contract_sha256=row['contract_sha256'],
                occurrences=len(row['occurrences']), scientific_review='PENDING', author_acceptance='PENDING')
