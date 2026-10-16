"""Explicit layout constraints, without automatic rearrangement or scientific inference."""
import math
from scientific_gate import indexed
from core import GateError


def geometry_index(graph):
    rows = indexed([*graph['objects'], *graph['text_objects'], *graph['arrow_objects'], *graph['groups']])
    result = {}
    for key, row in rows.items():
        box = row['bbox']
        if len(box) != 4 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in box) or box[2] < box[0] or box[3] < box[1]:
            raise GateError('INVALID_LAYOUT_BBOX: ' + key)
        result[key] = box
    return rows, result


def check_layout(graph, contract=None):
    rows, boxes = geometry_index(graph)
    width, height = graph['canvas']['width'], graph['canvas']['height']
    findings = []
    for key, b in boxes.items():
        if b[0] < -.001 or b[1] < -.001 or b[2] > width+.001 or b[3] > height+.001:
            findings.append(dict(id='outside:'+key, object_ids=[key], kind='outside_canvas'))
    checks = []
    for rule in (contract or {}).get('constraints', []):
        ids = rule['object_ids']; kind = rule['kind']; tolerance = rule.get('tolerance_px', .001)
        if not ids or any(key not in boxes for key in ids) or not isinstance(tolerance, (float,int)) or not math.isfinite(tolerance) or tolerance < 0:
            raise GateError('LAYOUT_CONSTRAINT_INVALID: ' + rule['id'])
        if kind in ('contains', 'disjoint', 'min_gap'):
            if len(ids) != 2: raise GateError('LAYOUT_PAIR_REQUIRED')
            a, b = (boxes[key] for key in ids)
            if kind == 'contains':
                margin = rule.get('margin_px', 0)
                passed = a[0]+margin <= b[0]+tolerance and a[1]+margin <= b[1]+tolerance and a[2]-margin >= b[2]-tolerance and a[3]-margin >= b[3]-tolerance
            elif kind == 'disjoint':
                passed = min(a[2], b[2])-max(a[0],b[0]) <= tolerance or min(a[3],b[3])-max(a[1],b[1]) <= tolerance
            else:
                gap = rule['minimum_px']; axis = rule.get('axis','x')
                if axis not in ('x','y') or gap < 0: raise GateError('LAYOUT_GAP_INVALID')
                i = 0 if axis == 'x' else 1
                passed = b[i]-a[i+2] >= gap-tolerance or a[i]-b[i+2] >= gap-tolerance
        elif kind == 'aligned':
            edge = rule.get('edge','left')
            if edge not in ('left','top','right','bottom','center_x','center_y'): raise GateError('LAYOUT_ALIGNMENT_INVALID')
            def value(b):
                return {'left':b[0],'top':b[1],'right':b[2],'bottom':b[3], 'center_x':(b[0]+b[2])/2, 'center_y':(b[1]+b[3])/2}[edge]
            values = [value(boxes[key]) for key in ids]; passed = max(values)-min(values) <= tolerance
        elif kind == 'min_font_pt':
            minimum = rule['minimum_pt']
            if minimum <= 0: raise GateError('MINIMUM_FONT_INVALID')
            scale = graph['geometry']['coordinate_transform']['scale_pt_per_px']
            if any(rows[key]['geometry']['kind'] != 'TEXT' for key in ids): raise GateError('FONT_CONSTRAINT_REQUIRES_TEXT')
            passed = all(rows[key]['geometry']['data']['font_size']*scale >= minimum for key in ids)
        else: raise GateError('UNKNOWN_LAYOUT_CONSTRAINT: ' + kind)
        checks.append(dict(id=rule['id'], kind=kind, object_ids=ids, passed=passed))
        if not passed: findings.append(dict(id=rule['id'], object_ids=ids, kind=kind))
    return dict(status='PASS' if not findings else 'FAIL', findings=findings, declared_checks=checks,
                auto_rearranged=False, scope='Declared boxes and constraints; no automatic text metrics or general visual acceptance')
