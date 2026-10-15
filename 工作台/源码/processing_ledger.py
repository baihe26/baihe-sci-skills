"""Honest per-element editability and retained-pixel ledger; no image manipulation."""
from core import GateError
from scientific_gate import indexed


def validate_ledger(ledger):
    rows = indexed(ledger['elements'])
    required = set(ledger['required_ids'])
    if not required <= set(rows):
        raise GateError('REQUIRED_ELEMENTS_UNACCOUNTED')
    for row in rows.values():
        if not row.get('source_ref') or not row.get('output_ids'):
            raise GateError('ELEMENT_PROVENANCE_OR_OUTPUT_MISSING')
        if row.get('uncertain') and row.get('review_status') == 'APPROVED':
            raise GateError('UNCERTAINTY_SILENTLY_APPROVED')
        if row['treatment'] == 'retained_pixels':
            if row['editability'] != 'MOVE_SCALE_REPLACE' or not row.get('source_sha256'):
                raise GateError('RETAINED_PIXELS_NOT_FULL_NATIVE')
            box = row.get('crop_box_normalized', [0, 0, 1, 1])
            if len(box) != 4 or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
                raise GateError('CROP_BOX_INVALID')
            if row.get('content_kind') not in ('scientific_image', 'photograph', 'texture'):
                raise GateError('RASTER_SUBSTITUTE_FOR_SEMANTIC_OBJECT')
        elif row['treatment'] not in ('native_text', 'native_geometry', 'editable_path', 'native_bound_connector'):
            raise GateError('UNKNOWN_ELEMENT_TREATMENT')
    # Semantic rectangles/arrows/text must be separately accounted; overlapping crops do not earn native credit.
    native_required = set(ledger.get('native_required_ids', []))
    if any(rows[key]['treatment'] == 'retained_pixels' for key in native_required):
        raise GateError('REQUIRED_NATIVE_ELEMENT_RASTERIZED')
    return dict(status='PASS', required=len(required), accounted=len(rows),
                native_count=sum(r['treatment'] != 'retained_pixels' for r in rows.values()),
                retained_pixel_count=sum(r['treatment'] == 'retained_pixels' for r in rows.values()),
                scope='ACCOUNTING_ONLY_NOT_VISUAL_OR_SCIENTIFIC_ACCEPTANCE')


def from_scene(graph):
    rows = []
    for key in ('objects', 'arrow_objects', 'text_objects'):
        for o in graph[key]:
            text = key == 'text_objects'
            relation = key == 'arrow_objects'
            rows.append(dict(id=o['id'], source_ref=dict(scientific_refs=o['scientific_refs'], layer_id=o['layer_id']),
                             output_ids=[o['id']], treatment='native_text' if text else 'editable_path' if relation else 'native_geometry',
                             editability='TEXT' if text else 'PATH_NODES_SCRIPT_MAINTAINED' if relation else 'MOVE_SCALE_STYLE',
                             uncertain=False, review_status='PENDING'))
    ledger = dict(schema_version='element-ledger-0.1', required_ids=[r['id'] for r in rows],
                  native_required_ids=[r['id'] for r in rows], elements=rows,
                  source='APPROVED_SCENE_CONTRACT', scientific_review='PENDING', visual_review='PENDING')
    ledger['check'] = validate_ledger(ledger)
    return ledger


def bounded_review(rounds, max_rounds=2):
    """Return an advisory next action; never claims a critic actually ran."""
    if not 1 <= max_rounds <= 5:
        raise GateError('REVIEW_BUDGET_INVALID')
    previous = None
    for row in rounds:
        issues = set(row['unresolved_issue_ids'])
        if previous is not None and issues and not issues < previous:
            return dict(status='STOP_NO_STRICT_PROGRESS', automatic_retry=False, unresolved=sorted(issues))
        previous = issues
    issues = previous if previous is not None else set()
    status = 'NOT_REVIEWED' if not rounds else 'PASS_RECORDED_SCOPE' if not issues else 'STOP_BUDGET' if len(rounds) >= max_rounds else 'TARGETED_FIX_REQUIRED'
    return dict(status=status, automatic_retry=False, unresolved=sorted(issues), max_rounds=max_rounds)
