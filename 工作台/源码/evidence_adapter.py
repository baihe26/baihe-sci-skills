"""Map already acquired evidence to figure claims. Does not replace paper reading."""
import math
from paths import sha, Path
from core import GateError
from scientific_gate import indexed, resolve_file


def check_evidence(contract, base, spec):
    blocks = indexed(contract.get('source_blocks', []))
    evidence = indexed(contract.get('evidence', []))
    claims = indexed(contract.get('claims', []))
    known_claims = {c['id'] for c in spec['scientific_claims']}
    if not set(claims) <= known_claims: raise GateError('EVIDENCE_FIGURE_CLAIM_UNRESOLVED')
    sources = []
    for key, row in blocks.items():
        path = resolve_file(base, row['path'])
        if not path.is_file() or sha(path) != row['sha256']: raise GateError('EVIDENCE_SOURCE_HASH_CONFLICT: '+key)
        if 'page' in row and (type(row['page']) is not int or row['page'] < 1): raise GateError('EVIDENCE_PAGE_INVALID')
        if 'bbox_normalized' in row:
            b=row['bbox_normalized']
            if len(b)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b) or not 0 <= b[0] < b[2] <= 1 or not 0 <= b[1] < b[3] <= 1: raise GateError('EVIDENCE_BBOX_INVALID')
        quote_verified=False
        if row.get('source_kind') == 'text' and row.get('quote'):
            if row['quote'] not in path.read_text(encoding='utf-8-sig'): raise GateError('EVIDENCE_QUOTE_NOT_FOUND')
            quote_verified=True
        sources.append(dict(id=key,sha256=row['sha256'],quote_verified=quote_verified,
                            locator_verified=False if row.get('page') or row.get('bbox_normalized') else None))
    for key, row in evidence.items():
        if not row.get('source_block_ids') or not set(row['source_block_ids']) <= set(blocks): raise GateError('EVIDENCE_BLOCK_UNRESOLVED: '+key)
    unresolved=[]
    for key, row in claims.items():
        if not row.get('links'): raise GateError('EVIDENCE_LINK_REQUIRED: '+key)
        for link in row['links']:
            if link['evidence_id'] not in evidence or link['relation'] not in ('supports','limits','contradicts','mixed'): raise GateError('EVIDENCE_LINK_INVALID')
            if link['relation'] != 'supports': unresolved.append(dict(claim_id=key,**link))
    for row in contract.get('decisions', []):
        if row.get('status') not in ('PROPOSED','CONFIRMED','REJECTED'): raise GateError('EVIDENCE_DECISION_STATUS_INVALID')
        if row['status']=='CONFIRMED' and not row.get('confirmation_source'): raise GateError('AUTHOR_CONFIRMATION_SOURCE_REQUIRED')
    return dict(status='MAPPED_NOT_SCIENTIFICALLY_VERIFIED',source_blocks=sources,
                evidence_count=len(evidence),mapped_claim_ids=sorted(claims),unresolved_links=unresolved,
                scientific_review='PENDING',automatic_adoption=False)
