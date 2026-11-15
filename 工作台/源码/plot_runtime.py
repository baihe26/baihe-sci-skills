"""Prepare explicit real-table jobs with the configured, existing EditaPlot engine.

No native activation occurs here. The current project can supply physical style
values; legacy renderer defaults are retained only for fields it did not change.
"""
from dataclasses import replace
from pathlib import Path
import math
import sys

from paths import PLOT, read
from core import GateError
from plot_sources import inspect_plot_task, reference, table, _require, curve_x_type


STYLE_FIELDS = {
    'page_width_cm', 'page_height_cm', 'layer_left_percent', 'layer_top_percent',
    'layer_width_percent', 'layer_height_percent', 'font_family',
    'axis_title_size_pt', 'tick_label_size_pt', 'legend_size_pt',
    'plot_line_width_pt', 'frame_line_width_pt', 'major_tick_length_pt',
    'minor_tick_length_pt', 'error_bar_width_pt', 'bar_border_width_pt',
    'fill_transparency_percent', 'x_minor_ticks_between_majors',
}


def apply_task_style(preparation, style_request):
    """Display-only adaptation; no universal paper sizes or rounded data values."""
    if not style_request:
        return preparation
    _require(set(style_request) <= STYLE_FIELDS, 'PLOT_STYLE_FIELD_UNSUPPORTED')
    for key, value in style_request.items():
        if key == 'font_family':
            _require(isinstance(value, str) and value.strip() and not any(c in value for c in '\r\n\x00;'),
                     'PLOT_FONT_INVALID')
        else:
            _require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                     and (value >= 0 if key in ('layer_left_percent', 'layer_top_percent', 'minor_tick_length_pt',
                                              'fill_transparency_percent', 'x_minor_ticks_between_majors') else value > 0),
                     'PLOT_STYLE_VALUE_INVALID: ' + key)
    xps = hasattr(preparation, 'visual_contract')
    style = preparation.visual_contract.figure_style if xps else preparation.plot_spec.display_plan.figure_style
    _require(style is not None, 'PLOT_STYLE_ADAPTER_UNSUPPORTED')
    adapted = replace(style, **style_request)
    _require(adapted.layer_left_percent + adapted.layer_width_percent <= 100 and
             adapted.layer_top_percent + adapted.layer_height_percent <= 100 and
             0 <= adapted.fill_transparency_percent <= 100, 'PLOT_STYLE_OUTSIDE_PAGE')
    if xps:
        from origin_sciplot.xps_workflow import replace_xps_visual_contract
        return replace_xps_visual_contract(preparation, replace(preparation.visual_contract, figure_style=adapted))
    from origin_sciplot.scientific_workflow import _scientific_plan_digest
    spec = replace(preparation.plot_spec, display_plan=replace(preparation.plot_spec.display_plan, figure_style=adapted))
    return replace(preparation, plot_spec=spec, plan_digest=_scientific_plan_digest(preparation, spec))


def prepare_native(task_path):
    audit = inspect_plot_task(task_path)
    task_path = Path(task_path).resolve()
    task = read(task_path)
    _require(task['operation'] == 'render_table', 'PLOT_RENDER_TABLE_OPERATION_REQUIRED')
    base = task_path.parent
    render_ref = task['render_table']
    data = reference(render_ref, base)
    # The source may be XLS/Origin; the adopted render table is a transparent CSV.
    _require(data.suffix.lower() == '.csv' and render_ref.get('header_row', 1) == 1 and
             render_ref.get('delimiter', ',') == ',',
             'PLOT_NATIVE_NORMALIZED_CSV_REQUIRED: 保留原表，另提供首行为列名的核对后 CSV。')
    headers, rows = table(render_ref, base)
    for curve in task['curves']:
        _require(curve['display'].get('rows', [1, len(rows)]) == [1, len(rows)] and
                 not curve['display'].get('excluded_rows'), 'PLOT_NATIVE_TABLE_RANGE_MISMATCH')
        unsupported_style = set(curve.get('style', {})) - {'sample_markers'}
        _require(not unsupported_style,
                 'PLOT_SERIES_STYLE_HANDOFF_REQUIRED: 当前表入口不逐曲线写入 ' + ', '.join(sorted(unsupported_style)) +
                 '；请用已支持的整图 physical_style/注册调色板，或交现有原生精确样式工具，不能只登记不应用。')
        _require(not curve.get('legend'),
                 'PLOT_LEGEND_POSITION_HANDOFF_REQUIRED: 显式图例几何需由原生工具实施；不能把核对记录当作已经排好。')
    runtime = PLOT / 'vendor/editaplot/runtime'
    _require((runtime / 'src/origin_sciplot/template_registry.py').is_file(), 'PLOT_RUNTIME_NOT_CONFIGURED')
    sys.path.insert(0, str(runtime / 'src'))
    from origin_sciplot.template_registry import TemplateRegistry
    from origin_sciplot.scientific_workflow import ScientificColumnMapping, prepare_scientific, _scientific_plan_digest
    from origin_sciplot.xps_workflow import XpsColumnMapping, prepare_xps, _xps_plan_digest
    backend = task['backend']
    template_id = backend['template_id']
    manifest = TemplateRegistry().get(template_id)
    mapping = backend['column_mapping']
    mapped_y = {c['display']['y'] for c in task['curves']}
    mapped_x = {c['display']['x'] for c in task['curves']}
    _require(len(mapped_y) == len(task['curves']),
             'PLOT_DUPLICATE_RENDER_COLUMN: 同一显示列不能被登记为多个实际绘制组；长表分组需专用适配。')
    if template_id == 'xps':
        kwargs = dict(mapping)
        for key in ('background', 'envelope', 'residual'):
            kwargs.setdefault(key, None)
        for key in ('components', 'ignored'):
            kwargs[key] = tuple(kwargs.get(key, []))
        prep = prepare_xps(data, column_mapping=XpsColumnMapping(**kwargs))
        used_y = {s.column for s in prep.plot_spec.series if s.role != 'residual'}
        _require(mapped_x == {prep.roles.x} and mapped_y == used_y, 'PLOT_NATIVE_SERIES_COVERAGE_MISMATCH')
        _require(all(c.get('display_energy_kind') == prep.detection.energy_kind for c in task['curves']),
                 'PLOT_NATIVE_ENERGY_KIND_MISMATCH')
    else:
        _require(isinstance(mapping.get('assignments'), dict) and set(mapping['assignments']) == set(headers),
                 'PLOT_NATIVE_ALL_COLUMNS_MUST_HAVE_ROLES')
        prep = prepare_scientific(data, template_id, column_mapping=ScientificColumnMapping(
            assignments=tuple(mapping['assignments'].items()), plot_mode=mapping.get('plot_mode')))
        _require(mapped_y == {s.source_column for s in prep.plot_spec.series}, 'PLOT_NATIVE_SERIES_COVERAGE_MISMATCH')
        xtype = {curve_x_type(c, task) for c in task['curves']}
        _require(len(xtype) == 1, 'PLOT_MIXED_X_TYPES_NEED_ADAPTER')
        native_x = prep.plot_spec.category_column if xtype == {'category'} else prep.plot_spec.x_column
        _require(mapped_x == {native_x}, 'PLOT_NATIVE_X_BINDING_MISMATCH')
        by_column = {c['display']['y']: c for c in task['curves']}
        declared_errors = {col for col, role in mapping['assignments'].items() if role == 'error'}
        used_errors = {s.error_column for s in prep.plot_spec.series if s.error_column}
        _require(declared_errors == used_errors, 'PLOT_NATIVE_UNUSED_OR_HIDDEN_ERROR_ROLE')
        for series in prep.plot_spec.series:
            curve = by_column[series.source_column]
            uncertainty = curve.get('uncertainty')
            if series.error_column:
                _require(uncertainty is not None, 'PLOT_NATIVE_ERROR_BINDING_REQUIRED: ' + series.error_column)
                error_display = uncertainty['display']
                _require(error_display['y'] == series.error_column and error_display['x'] == curve['display']['x']
                         and reference(error_display['table'], base) == data
                         and error_display.get('rows', [1, len(rows)]) == [1, len(rows)]
                         and not error_display.get('excluded_rows'), 'PLOT_NATIVE_ERROR_COLUMN_MISMATCH')
                _require(str(series.error_kind).casefold() == uncertainty['definition'].casefold(), 'PLOT_NATIVE_ERROR_DEFINITION_MISMATCH: ' +
                         str(series.error_kind) + ' / ' + uncertainty['definition'])
            elif uncertainty:
                raise GateError('PLOT_DECLARED_ERROR_NOT_RENDERED')
            _require(not series.lower_column and not series.upper_column,
                     'PLOT_NATIVE_INTERVAL_BINDINGS_REQUIRED: 当前薄入口需专用上下界数组适配，不能省略核对。')
        transform = prep.plot_spec.display_transform
        _require(transform == 'identity' or backend.get('display_transform') == transform,
                 'PLOT_BACKEND_TRANSFORM_NOT_DECLARED: ' + str(transform))
    _require(not prep.requires_confirmation, 'PLOT_NATIVE_ROLES_UNRESOLVED')
    if task.get('axis_titles'):
        _require(template_id != 'xps', 'PLOT_XPS_TITLE_COMES_FROM_ENERGY_PLAN')
        _require(set(task['axis_titles']) <= {'x', 'y'}, 'PLOT_AXIS_TITLE_FIELD_UNSUPPORTED')
        from origin_sciplot.scientific_workflow import apply_scientific_text_overrides
        titles = {}
        for axis, row in task['axis_titles'].items():
            reference(row.get('evidence'), base)
            _require(row.get('title') and row.get('reason'), 'PLOT_AXIS_TITLE_EVIDENCE_REQUIRED')
            titles[axis + '_title'] = row['title']
        prep = apply_scientific_text_overrides(prep, **titles)
    if backend.get('palette_id'):
        _require(template_id != 'xps', 'PLOT_XPS_EXACT_COLOR_ADAPTER_REQUIRED')
        from origin_sciplot.scientific_workflow import apply_scientific_palette_override
        prep = apply_scientific_palette_override(prep, palette_id=backend['palette_id'])
    aliases = {c['display']['y']: c['display_label'] for c in task['curves']}
    series = tuple(replace(s, label=aliases.get(s.column if template_id == 'xps' else s.source_column, s.label))
                   for s in prep.plot_spec.series)
    spec = replace(prep.plot_spec, series=series)
    prep = replace(prep, plot_spec=spec)
    prep = replace(prep, plan_digest=_xps_plan_digest(prep) if template_id == 'xps' else _scientific_plan_digest(prep, spec))
    prep = apply_task_style(prep, task.get('physical_style', {}))
    # Shared object remains fully source-bound; downstream renderer reads it.
    return task, audit, manifest, prep
