"""Read-only numeric provenance and display checks for real plot tasks.

This layer does not infer sample identity, peak assignments, statistics or energy
reference conventions. It checks the explicit mapping supplied by the host and
keeps an existing Origin source separate from a tabular export of that source.
"""
from pathlib import Path
import csv
import math
import re
import unicodedata
from bisect import bisect_right

from paths import read, sha
from core import GateError


def _require(ok, message):
    if not ok:
        raise GateError(message)


def reference(ref, base):
    """Bind a local file without writing it or choosing the newest filename."""
    _require(isinstance(ref, dict) and ref.get('path') and ref.get('sha256'),
             'PLOT_SOURCE_REFERENCE_REQUIRED: 请给出具体源文件及其当前校验值。')
    path = (Path(base) / ref['path']).resolve()
    _require(path.is_file(), 'PLOT_SOURCE_MISSING: ' + str(path))
    _require(sha(path) == ref['sha256'], 'PLOT_SOURCE_CHANGED: ' + str(path))
    return path


def table(ref, base):
    """Read explicit sheets/header rows; never silently choose the first sheet."""
    path = reference(ref, base)
    header_row = ref.get('header_row', 1)
    _require(isinstance(header_row, int) and not isinstance(header_row, bool) and header_row >= 1,
             'PLOT_HEADER_ROW_INVALID')
    suffix = path.suffix.lower()
    if suffix in ('.csv', '.tsv', '.txt'):
        delimiter = ref.get('delimiter', '\t' if suffix == '.tsv' else ',')
        _require(isinstance(delimiter, str) and len(delimiter) == 1, 'PLOT_DELIMITER_REQUIRED')
        with path.open(encoding=ref.get('encoding', 'utf-8-sig'), newline='') as handle:
            rows = list(csv.reader(handle, delimiter=delimiter))
    elif suffix == '.xlsx':
        import openpyxl
        _require(ref.get('sheet'), 'PLOT_WORKSHEET_REQUIRED: 请指定工作表，不能按第一张表猜测。')
        with path.open('rb') as handle:
            book = openpyxl.load_workbook(handle, read_only=True, data_only=False)
            try:
                _require(ref['sheet'] in book.sheetnames, 'PLOT_WORKSHEET_MISSING')
                rows = list(book[ref['sheet']].iter_rows(values_only=True))
            finally:
                book.close()
        _require(not any(isinstance(v, str) and v.startswith('=') for row in rows[header_row:] for v in row),
                 'PLOT_FORMULA_VALUES_REQUIRED: 此表含公式；请保留公式原件并提供核对过的数值导出。')
    elif suffix == '.xls':
        _require(ref.get('sheet'), 'PLOT_WORKSHEET_REQUIRED')
        import pandas as pd
        frame = pd.read_excel(path, sheet_name=ref['sheet'], header=None, dtype=object)
        rows = frame.where(frame.notna(), None).values.tolist()
    else:
        raise GateError('PLOT_TABLE_FORMAT_UNSUPPORTED: 支持 CSV、TSV、明确分隔符的 TXT、XLS、XLSX；Origin 工程需保留另行登记。')
    _require(len(rows) >= header_row, 'PLOT_HEADER_MISSING')
    headers = [str(v).strip() if v is not None else '' for v in rows[header_row - 1]]
    _require(all(headers) and len(set(headers)) == len(headers), 'PLOT_COLUMN_NAMES_AMBIGUOUS')
    result = []
    for index, row in enumerate(rows[header_row:], 1):
        _require(len(row) <= len(headers), 'PLOT_ROW_HAS_EXTRA_VALUES: ' + str(index))
        result.append(dict(zip(headers, [*row, *([''] * (len(headers) - len(row)))])))
    return headers, result


def _number(value, where):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise GateError('PLOT_NONNUMERIC_VALUE: ' + where)
    _require(math.isfinite(number), 'PLOT_NONFINITE_VALUE: ' + where)
    return number


def xy_series(binding, base):
    headers, rows = table(binding['table'], base)
    xcol, ycol = binding.get('x'), binding.get('y')
    _require(xcol in headers and ycol in headers and xcol != ycol, 'PLOT_XY_COLUMNS_REQUIRED')
    span = binding.get('rows', [1, len(rows)])
    _require(isinstance(span, list) and len(span) == 2 and
             all(isinstance(v, int) and not isinstance(v, bool) for v in span) and
             1 <= span[0] <= span[1] <= len(rows), 'PLOT_ROW_RANGE_INVALID')
    excluded = binding.get('excluded_rows', [])
    _require(all(isinstance(item, dict) and isinstance(item.get('row'), int) and
                 span[0] <= item['row'] <= span[1] and item.get('reason') for item in excluded),
             'PLOT_EXCLUSION_REASON_REQUIRED')
    excluded_ids = {item['row'] for item in excluded}
    _require(len(excluded_ids) == len(excluded), 'PLOT_DUPLICATE_EXCLUSION')
    values = []
    for index in range(span[0], span[1] + 1):
        if index in excluded_ids:
            continue
        row = rows[index - 1]
        y = _number(row[ycol], f'{ycol}, 数据行 {index}')
        if binding.get('x_type', 'continuous') == 'category':
            x = str(row[xcol]).strip() if row[xcol] is not None and str(row[xcol]).strip() else None
        else:
            _require(binding.get('x_type', 'continuous') == 'continuous', 'PLOT_X_TYPE_INVALID')
            x = _number(row[xcol], f'{xcol}, 数据行 {index}')
        _require(not (x is None and y is not None), 'PLOT_X_COORDINATE_MISSING: ' + str(index))
        # Missing pairs remain a break in the curve, never silently joined.
        values.append([x, y])
    _require(any(x is not None and y is not None for x, y in values), 'PLOT_EMPTY_SERIES')
    return values, dict(table_rows=len(rows), selected_rows=span, excluded_rows=excluded,
                        finite_points=sum(x is not None and y is not None for x, y in values),
                        gap_rows=sum(x is None or y is None for x, y in values))


def transformed(values, operations, base):
    """Only documented affine/unit/display or energy conversions; no smoothing."""
    result = [list(pair) for pair in values]
    for op in operations:
        _require(op.get('reason') and op.get('evidence'), 'PLOT_TRANSFORM_EVIDENCE_REQUIRED')
        reference(op['evidence'], base)
        kind = op.get('kind')
        if kind == 'affine':
            _require(op.get('axis') in ('x', 'y'), 'PLOT_TRANSFORM_AXIS_REQUIRED')
            scale, offset = _number(op.get('scale'), 'scale'), _number(op.get('offset'), 'offset')
            _require(scale is not None and scale != 0 and offset is not None, 'PLOT_AFFINE_PARAMETERS_REQUIRED')
            axis = ('x', 'y').index(op['axis'])
            _require(not any(isinstance(pair[axis], str) for pair in result), 'PLOT_CATEGORY_NUMERIC_TRANSFORM_FORBIDDEN')
            for pair in result:
                if pair[axis] is not None:
                    pair[axis] = pair[axis] * scale + offset
        elif kind == 'energy':
            _require(not any(isinstance(pair[0], str) for pair in result), 'PLOT_ENERGY_REQUIRES_NUMERIC_X')
            _require({op.get('source_kind'), op.get('target_kind')} == {'binding', 'kinetic'},
                     'PLOT_ENERGY_CONVERSION_KIND_INVALID')
            hv = _number(op.get('photon_energy_eV'), 'photon_energy_eV')
            offset = _number(op.get('reference_offset_eV'), 'reference_offset_eV')
            _require(hv is not None and hv > 0 and offset is not None and op.get('reference_basis'),
                     'PLOT_ENERGY_REFERENCE_REQUIRED: 光子能量和零点约定都要有依据，不能默认扣除功函数。')
            for pair in result:
                if pair[0] is not None:
                    pair[0] = hv - pair[0] - offset
        else:
            raise GateError('PLOT_TRANSFORM_UNSUPPORTED: 不能用美化任务自动平滑、补峰或重拟合。')
    _require(all(v is None or isinstance(v, str) or math.isfinite(v) for pair in result for v in pair), 'PLOT_TRANSFORM_NONFINITE')
    return result


def _equal(left, right, abs_tol=0.0, rel_tol=0.0):
    return len(left) == len(right) and all(
        (a is None and b is None) or
        (isinstance(a, str) and isinstance(b, str) and a == b) or
        (a is not None and b is not None and not isinstance(a, str) and not isinstance(b, str)
         and math.isclose(a, b, abs_tol=abs_tol, rel_tol=rel_tol))
        for aa, bb in zip(left, right) for a, b in zip(aa, bb))


def energy_kind_from_header(column):
    """Recognize explicit energy names, never infer an energy scale from values.

    Use the existing XPS vocabulary, with lexical boundaries rather than exact
    whole-title equality: acquisition/calibration notes may surround a name.
    Ambiguous titles naming both scales require evidence, not a guessed winner.
    """
    title = unicodedata.normalize('NFKC', str(column)).strip()
    folded = title.casefold()
    compact = ''.join(character for character in folded if character.isalnum())
    names = {
        'binding': ('binding', 'bindingenergy', 'be', '结合能', '束缚能'),
        'kinetic': ('kinetic', 'kineticenergy', 'ke', '动能', '动力学能'),
    }
    found = set()
    for kind, aliases in names.items():
        if compact in {alias + unit for alias in aliases for unit in ('', 'e', 'ev')}:
            found.add(kind)
        # Full English energy names may be separated by whitespace, underscores
        # or hyphens, and may have a unit attached without a space.
        full_name = kind + r'[\s_\-]*energy'
        if re.search(r'(?<![a-z0-9])' + full_name + r'(?=$|[^a-z0-9]|ev\b)', folded):
            found.add(kind)
        if any(alias in folded for alias in aliases if not alias.isascii()):
            found.add(kind)
    # Abbreviations in headers may carry a unit or be standalone label clauses
    # (e.g. "as acquired: ke / eV"). Do not read the English verb "be" in
    # "to be processed" or fragments in "BEad" as an energy coordinate.
    clauses = {part.strip().casefold() for part in re.split(r'[,;:/|()\[\]{}\-–—]', title)}
    for match in re.finditer(r'(?<![a-z0-9])(be|ke)(?=$|[^a-z0-9]|ev\b)', folded):
        token = title[match.start():match.end()]
        tail = folded[match.end():]
        has_unit = bool(re.match(r'\s*(?:[/\[(]\s*)?(?:ev|e)\b', tail))
        if token.isupper() or has_unit or match.group() in clauses:
            found.add('binding' if match.group() == 'be' else 'kinetic')
    return next(iter(found)) if len(found) == 1 else 'ambiguous' if found else None


def audit_curve(curve, base):
    x_type = curve.get('x_type', curve['source'].get('x_type', 'continuous'))
    source_values, source_info = xy_series(dict(curve['source'], x_type=x_type), base)
    actual, actual_info = xy_series(dict(curve['display'], x_type=x_type), base)
    operations = curve.get('transforms', [])
    expected = transformed(source_values, operations, base)
    source_energy, target_energy = curve.get('source_energy_kind'), curve.get('display_energy_kind')
    if source_energy is not None or target_energy is not None:
        _require(source_energy in ('binding', 'kinetic') and target_energy in ('binding', 'kinetic'),
                 'PLOT_ENERGY_KIND_REQUIRED: 单调横坐标不能证明是结合能或动能。')
        for key, declared in (('source', source_energy), ('display', target_energy)):
            header_kind = energy_kind_from_header(curve[key]['x'])
            if header_kind is not None and header_kind != declared:
                correction = curve.get(key + '_energy_correction', {})
                _require(correction.get('header_kind') == header_kind and correction.get('resolved_kind') == declared
                         and correction.get('reason') and correction.get('evidence'),
                         'PLOT_ENERGY_HEADER_CONFLICT: ' + key + ' 列名标了另一能标或同时写了两种能标；需绑定证据解释标题与实际坐标，不能靠声明绕过。')
                reference(correction['evidence'], base)
        energy_ops = [op for op in operations if op.get('kind') == 'energy']
        if source_energy != target_energy:
            _require(len(energy_ops) == 1 and energy_ops[0]['source_kind'] == source_energy and
                     energy_ops[0]['target_kind'] == target_energy, 'PLOT_ENERGY_RELABEL_FORBIDDEN')
        else:
            _require(not energy_ops, 'PLOT_ENERGY_LABEL_CONVERSION_CONFLICT')
    elif any(op.get('kind') == 'energy' for op in operations):
        raise GateError('PLOT_ENERGY_KIND_REQUIRED')
    for axis in ('x', 'y'):
        units = curve.get(axis + '_units')
        if units and units.get('source') != units.get('display'):
            _require(any(op.get('kind') == 'affine' and op.get('axis') == axis for op in operations),
                     'PLOT_UNIT_RELABEL_FORBIDDEN: ' + axis)
    tolerance = curve.get('tolerance', {})
    abs_tol, rel_tol = tolerance.get('absolute', 0.0), tolerance.get('relative', 0.0)
    _require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
                 for v in (abs_tol, rel_tol)), 'PLOT_TOLERANCE_INVALID')
    _require(not (abs_tol or rel_tol) or tolerance.get('reason'), 'PLOT_TOLERANCE_REASON_REQUIRED')
    sampling = curve.get('display_sampling')
    warning = None
    if sampling:
        _require(sampling.get('reason') and sampling.get('authorization') and curve.get('native_full'),
                 'PLOT_DOWNSAMPLING_EVIDENCE_REQUIRED')
        native, _ = xy_series(curve['native_full'], base)
        _require(_equal(expected, native, abs_tol, rel_tol), 'PLOT_NATIVE_FULL_ARRAY_MISMATCH')
        indices = sampling.get('indices', [])
        _require(indices and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(expected) for v in indices)
                 and indices == sorted(set(indices)), 'PLOT_SAMPLE_INDICES_INVALID')
        finite = [i for i, (x, y) in enumerate(expected) if x is not None and y is not None]
        protected = {0, len(expected) - 1, min(finite, key=lambda i: expected[i][1]),
                     max(finite, key=lambda i: expected[i][1]), *sampling.get('protected_indices', [])}
        # Keep missing rows and adjacent points, otherwise a gap becomes a line.
        for i, pair in enumerate(expected):
            if any(v is None for v in pair):
                protected.update(j for j in (i - 1, i, i + 1) if 0 <= j < len(expected))
        _require(protected <= set(indices), 'PLOT_DOWNSAMPLING_REMOVES_FEATURE_OR_GAP')
        expected = [expected[i] for i in indices]
        warning = '显示抽稀已记录；完整原生数组已核对，局部窄峰及图面仍需实际检查。'
    _require(_equal(expected, actual, abs_tol, rel_tol),
             f'PLOT_ARRAY_MISMATCH: {curve.get("id", "未命名曲线")}；源映射后 {len(expected)} 行，显示 {len(actual)} 行，列值或行数不一致。')
    return dict(id=curve['id'], status='PASS', source=source_info, display=actual_info,
                x_type=x_type,
                source_columns=[curve['source']['x'], curve['source']['y']],
                display_columns=[curve['display']['x'], curve['display']['y']],
                transforms=operations, warning=warning)


def curve_x_type(curve, task):
    explicit = curve.get('x_type') or curve.get('source', {}).get('x_type')
    role = task.get('backend', {}).get('column_mapping', {}).get('assignments', {}).get(curve['display']['x'])
    if role == 'category':
        _require(explicit in (None, 'category'), 'PLOT_CATEGORY_ROLE_CONFLICT')
        return 'category'
    return explicit or 'continuous'


def audit_uncertainty(curve, base, x_type='continuous'):
    uncertainty = curve.get('uncertainty')
    if not uncertainty:
        return None
    _require(uncertainty.get('definition') in ('SD', 'SEM', 'SE', 'CI', 'range', 'custom') and
             uncertainty.get('source') and uncertainty.get('display') and uncertainty.get('evidence'),
             'PLOT_UNCERTAINTY_BINDINGS_REQUIRED: 请绑定误差原列、当前列、定义和依据。')
    reference(uncertainty['evidence'], base)
    for operation in uncertainty.get('transforms', []):
        if operation.get('kind') == 'affine' and operation.get('axis') == 'y':
            _require(operation.get('offset') == 0 and operation.get('scale', -1) > 0,
                     'PLOT_ERROR_OFFSET_FORBIDDEN: 误差幅度不能随中心曲线做显示平移。')
    item = dict(uncertainty, id=curve['id'] + ':uncertainty', x_type=x_type)
    report = audit_curve(item, base)
    values, _ = xy_series(dict(uncertainty['display'], x_type=x_type), base)
    _require(all(y is None or y >= 0 for _, y in values), 'PLOT_NEGATIVE_ERROR_MAGNITUDE')
    center, _ = xy_series(dict(curve['display'], x_type=x_type), base)
    _require([x for x, _ in values] == [x for x, _ in center], 'PLOT_ERROR_X_COORDINATES_MISMATCH')
    report['definition'] = uncertainty['definition']
    return report


def unsupported_annotations(task):
    """Do not accept and drop a request the current native vocabulary cannot draw."""
    fields = {'peak_labels', 'peak_annotations', 'annotations', 'leaders', 'reference_lines', 'significance_brackets'}
    for where, data in [('task', task), ('backend', task.get('backend', {})),
                        *[(c.get('id', 'curve'), c) for c in task.get('curves', [])]]:
        present = [key for key in fields if data.get(key)]
        if present:
            raise GateError('PLOT_ANNOTATION_HANDOFF_REQUIRED: ' + where + ' 请求了 ' + ', '.join(sorted(present)) +
                            '。此薄入口尚未施工这些对象；保留原逐峰指示要求，交既有 Origin/排图原生工具完成，再核对锚点和最终图，不能报已完成。')


def check_histogram(values, bin_edges, heights, mode='count'):
    """Verify explicit bins, including the closed rightmost edge."""
    _require(len(bin_edges) >= 2 and len(heights) == len(bin_edges) - 1 and
             all(math.isfinite(v) for v in [*values, *bin_edges, *heights]) and
             all(b > a for a, b in zip(bin_edges, bin_edges[1:])), 'PLOT_HISTOGRAM_BINS_INVALID')
    _require(mode in ('count', 'fraction', 'density'), 'PLOT_HISTOGRAM_MODE_INVALID')
    counts = [0] * len(heights)
    for value in values:
        _require(bin_edges[0] <= value <= bin_edges[-1], 'PLOT_HISTOGRAM_VALUE_OUTSIDE_BINS')
        counts[min(bisect_right(bin_edges, value) - 1, len(counts) - 1)] += 1
    _require(bool(values), 'PLOT_HISTOGRAM_EMPTY')
    expected = counts if mode == 'count' else [c / len(values) / (bin_edges[i + 1] - bin_edges[i] if mode == 'density' else 1)
                                             for i, c in enumerate(counts)]
    _require(all(math.isclose(a, b, abs_tol=1e-12, rel_tol=1e-12) for a, b in zip(expected, heights)),
             'PLOT_HISTOGRAM_HEIGHTS_MISMATCH')
    return dict(status='PASS', sample_count=len(values), bins=list(bin_edges), mode=mode)


def presentation_checks(request):
    """Checks requested semantics, not inferred visual success."""
    for curve in request.get('curves', []):
        style = curve.get('style', {})
        if request.get('plot_type') == 'continuous_spectrum':
            _require(not style.get('sample_markers'), 'PLOT_DENSE_SPECTRUM_SAMPLE_MARKERS')
        legend = curve.get('legend')
        if legend:
            for key in ('color', 'line_style', 'marker', 'line_width'):
                if key in style:
                    _require(legend.get(key) == style[key], 'PLOT_LEGEND_SERIES_MISMATCH: ' + key)
            if 'sample_center_y' in legend and 'text_bounds' in legend:
                bounds = legend['text_bounds']
                _require(len(bounds) == 4 and bounds[3] > 0, 'PLOT_LEGEND_BOUNDS_INVALID')
                _require(abs(legend['sample_center_y'] - (bounds[1] + bounds[3] / 2)) <=
                         legend.get('alignment_tolerance', bounds[3] * .1), 'PLOT_LEGEND_UNDERLINE_POSITION')
        if curve.get('error_column') and request.get('operation') != 'revise_origin':
            _require(curve.get('uncertainty') or (curve.get('error_definition') and curve.get('error_source')),
                     'PLOT_ERROR_DEFINITION_REQUIRED')
        if curve.get('significance'):
            _require(curve['significance'].get('comparison') and curve['significance'].get('test') and
                     curve['significance'].get('source'), 'PLOT_SIGNIFICANCE_EVIDENCE_REQUIRED')
    return True


def inspect_plot_task(task_path):
    """No native application is activated, no research file is modified."""
    task_path = Path(task_path).resolve()
    request = read(task_path)
    base = task_path.parent
    _require(request.get('schema_version') == 'plot-task-1', 'PLOT_TASK_SCHEMA_REQUIRED')
    _require(request.get('operation') in ('render_table', 'revise_origin'), 'PLOT_TASK_OPERATION_REQUIRED')
    _require(request.get('task_id') and request.get('authorization'), 'PLOT_TASK_SCOPE_REQUIRED')
    _require(request.get('curves'), 'PLOT_CURVE_BINDINGS_REQUIRED')
    unsupported_annotations(request)
    ids = [c.get('id') for c in request['curves']]
    _require(all(ids) and len(ids) == len(set(ids)), 'PLOT_CURVE_IDS_INVALID')
    for curve in request['curves']:
        _require(curve.get('group_id') and curve.get('display_label') and curve.get('identity_basis'),
                 'PLOT_SAMPLE_IDENTITY_REQUIRED')
        # Identity basis remains an explicit source reference, never a filename guess.
        reference(curve['identity_basis'], base)
        for key in ('error_source',):
            if curve.get(key):
                reference(curve[key], base)
        if curve.get('significance'):
            reference(curve['significance']['source'], base)
    results = []
    for curve in request['curves']:
        xtype = curve_x_type(curve, request)
        row = audit_curve(dict(curve, x_type=xtype), base)
        row['uncertainty'] = audit_uncertainty(curve, base, xtype)
        results.append(row)
    presentation_checks(request)
    if request['operation'] == 'revise_origin':
        parent = reference(request.get('parent_origin'), base)
        from task_context import load_context, require_parent_match
        require_parent_match(load_context(), parent)
        _require(parent.suffix.lower() in ('.opju', '.opj'), 'PLOT_ORIGIN_PARENT_REQUIRED')
        for curve in request['curves']:
            binding = curve.get('origin_binding', {})
            _require(all(binding.get(k) for k in ('graph', 'worksheet', 'x_column', 'y_column', 'rows')),
                     'PLOT_ORIGIN_BINDING_REQUIRED')
        status = 'SOURCE_TABLES_VERIFIED_NATIVE_BINDINGS_PENDING'
        next_action = '按已定位的原生图窗局部修改副本，再反读真实曲线绑定；此检查尚未读取 OPJU 内部。'
    else:
        reference(request.get('render_table'), base)
        for curve in request['curves']:
            _require(reference(curve['display']['table'], base) == reference(request['render_table'], base),
                     'PLOT_RENDER_TABLE_BINDING_MISMATCH')
        _require(request.get('backend', {}).get('template_id') and request['backend'].get('column_mapping'),
                 'PLOT_BACKEND_MAPPING_REQUIRED')
        status = 'SOURCE_TABLES_VERIFIED_NATIVE_PLAN_PENDING'
        next_action = '来源、列值和已声明变换通过；需核对活动引擎实际采用的系列与误差，再生产并做原生反读、重开和图面检查。'
    return dict(status=status, task=task_path.name, task_sha256=sha(task_path), curves=results,
                native_bindings='NOT_READ', native_reopen='NOT_RUN', visual='NOT_REVIEWED',
                author_acceptance='NOT_RECORDED', next_action=next_action)
