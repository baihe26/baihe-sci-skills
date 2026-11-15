"""Owned native processes for real-table rendering and scoped existing-plot edits."""
from pathlib import Path
import json
import sys
import re
import math

from paths import PLOT, read, save, sha, digest, load_file
from core import GateError, writable
from plot_sources import inspect_plot_task, reference, xy_series, _require, _equal


def render(task_path, out):
    from plot_runtime import prepare_native
    task, audit, manifest, prep = prepare_native(task_path)
    from origin_sciplot.output_manager import create_run_output
    from origin_sciplot.logging_utils import RunLogger
    from origin_sciplot.scientific_workflow import load_scientific_frame
    from origin_sciplot.xps_workflow import load_xps_frame
    from origin_sciplot.origin_backend.execution_context import require_interactive_origin_context
    from origin_sciplot.origin_backend.job_queue import origin_job_slot
    require_interactive_origin_context()
    data = reference(task['render_table'], Path(task_path).parent)
    output = create_run_output(data, manifest, out / '原生图')
    # Persist the exact prepared plan used below, including style/alias choices.
    payload = prep.to_dict() if hasattr(prep, 'to_dict') else __import__('dataclasses').asdict(prep)
    save(out / '原生绘图计划.json', payload)
    frame = (load_xps_frame if manifest.id == 'xps' else load_scientific_frame)(output.input_copy, prep)
    runner = load_file('baihe_real_plot_runner', manifest.runner_path)
    with origin_job_slot(job_kind='baihe-real-table-render'):
        result = runner.run(manifest, frame, output, RunLogger(output.run_log, output.output_dir),
                            keep_origin_open=False, preparation=prep)
    for path in (output.result_opju, output.result_png, output.result_pdf):
        _require(path.is_file() and path.stat().st_size > 0, 'PLOT_NATIVE_OUTPUT_MISSING: ' + path.name)
    save(out / '原生生产结果.json', dict(status='NATIVE_RENDERED_PENDING_REOPEN_AND_VISUAL',
         requested_style=task.get('physical_style', {}), current_runtime=str(PLOT),
         outputs={p.name: sha(p) for p in (output.result_opju, output.result_png, output.result_pdf)},
         upstream=result, source_recheck=inspect_plot_task(task_path),
         native_reopen='NOT_RUN', visual='NOT_REVIEWED', author_acceptance='NOT_RECORDED'))
    save(out / '原生工程与导出绑定.json', dict(schema_version='native-plot-binding-0.1',
         project=dict(sha256=sha(output.result_opju)),
         exports=[dict(sha256=sha(p), graph_id='NOT_INDEPENDENTLY_READ') for p in (output.result_png, output.result_pdf)],
         arrays=[], native_readback=dict(status='NOT_PERFORMED', method='origin_native', graph_bindings=[]),
         scope='已有 renderer 完成保存和自身反读；独立数组/曲线绑定对账和重开尚未执行。'))


def _snapshot(op):
    # Every retained worksheet is checked, not only the visible plotted columns.
    worksheets = {s.lt_range(False): json.dumps(s.to_df().to_dict(orient='split'), sort_keys=True, default=str)
                  for book in op.pages('w') for s in book}
    matrices = {s.lt_range(False): __import__('numpy').array(s.to_np2d()).tolist()
                for book in op.pages('m') for s in book}
    def finite(value):
        if isinstance(value, list):
            return [finite(v) for v in value]
        return None if isinstance(value, float) and not math.isfinite(value) else value
    return dict(worksheets=worksheets, matrices={k: finite(v) for k, v in matrices.items()})


def _bindings(op, task, base):
    from origin_sciplot.origin_backend.evidence_renderer import _read_shap_plot_binding
    result = []
    for i, curve in enumerate(task['curves']):
        b = curve['origin_binding']
        graph = op.find_graph(b['graph'])
        _require(graph is not None, 'PLOT_NATIVE_GRAPH_MISSING')
        layer_index, plot_index = b.get('layer', 1), b.get('plot_index')
        _require(isinstance(layer_index, int) and layer_index >= 1 and isinstance(plot_index, int) and plot_index >= 1,
                 'PLOT_NATIVE_LAYER_AND_PLOT_INDEX_REQUIRED')
        layer = graph[layer_index - 1]
        sheet = op.find_sheet('w', b['worksheet'])
        _require(sheet is not None, 'PLOT_NATIVE_WORKSHEET_MISSING')
        expected, _ = xy_series(curve['display'], base)
        actual = []
        xs, ys = sheet.to_list(b['x_column']), sheet.to_list(b['y_column'])
        _require(len(xs) == len(ys), 'PLOT_NATIVE_XY_LENGTH_MISMATCH')
        for x, y in zip(xs, ys):
            actual.append([None if isinstance(v, float) and not math.isfinite(v) else v for v in (x, y)])
        _require(b['rows'] == [1, len(actual)] and len(actual) == len(expected),
                 'PLOT_NATIVE_PARTIAL_RANGE_UNSUPPORTED: 此局部编辑入口核对完整绑定列；分段图需专用范围适配。')
        _require(_equal(expected, actual, 1e-12, 1e-12), 'PLOT_NATIVE_TABLE_VALUES_MISMATCH')
        identity = _read_shap_plot_binding(op, layer, f'[{graph.name}]{layer_index}!{plot_index}',
                                           sheet, b['x_column'], b['y_column'], prefix=f'baihe{i}')
        result.append(dict(id=curve['id'], identity=identity, points=len(actual), graph=graph.name,
                           values_sha256=digest(actual), source_sha256=curve['display']['table']['sha256'],
                           raw_source_sha256=curve['source']['table']['sha256'],
                           locator=f'{b["worksheet"]}: {b["x_column"]}, {b["y_column"]}; rows {b["rows"]}'))
    return result


def _changes(op, task, apply):
    """Small, executable edit vocabulary. No arbitrary LabTalk or source edits."""
    from origin_sciplot.origin_backend.base_style_contract import pt_to_origin_width_units
    result = []
    for change in task.get('native_edits', []):
        _require(change.get('graph') in {c['origin_binding']['graph'] for c in task['curves']},
                 'PLOT_EDIT_GRAPH_OUTSIDE_SCOPE')
        graph = op.find_graph(change['graph'])
        graph.activate()
        index = change.get('layer', 1)
        _require(isinstance(index, int) and index >= 1, 'PLOT_EDIT_LAYER_INVALID')
        layer = graph[index - 1]
        kind = change.get('kind')
        values = change.get('values', {})
        _require(values, 'PLOT_EDIT_VALUES_REQUIRED')
        observed = {}
        if kind == 'label':
            _require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', change.get('name', '')) is not None,
                     'PLOT_LABEL_NAME_INVALID')
            _require(set(values) <= {'left', 'top', 'fsize'}, 'PLOT_LABEL_EDIT_UNSUPPORTED')
            label = layer.label(change['name'])
            _require(label is not None, 'PLOT_NATIVE_LABEL_MISSING')
            for key, target in values.items():
                _require(isinstance(target, (int, float)) and math.isfinite(target) and (key != 'fsize' or target > 0),
                         'PLOT_EDIT_VALUE_INVALID')
                if apply:
                    label.set_float(key, target)
                observed[key] = label.get_float(key)
        elif kind == 'axis_tick_font':
            _require(change.get('axis') in ('x', 'y') and set(values) == {'font_pt'}, 'PLOT_AXIS_EDIT_UNSUPPORTED')
            target = values['font_pt']
            _require(isinstance(target, (int, float)) and math.isfinite(target) and target > 0, 'PLOT_EDIT_VALUE_INVALID')
            prop = change['axis'] + '.label.pt'
            if apply:
                layer.set_float(prop, target)
            observed['font_pt'] = layer.get_float(prop)
        elif kind == 'curve_width':
            _require(set(values) == {'line_width_pt'} and values['line_width_pt'] > 0, 'PLOT_CURVE_EDIT_UNSUPPORTED')
            curve = next((c for c in task['curves'] if c['id'] == change.get('curve_id')), None)
            _require(curve is not None and curve['origin_binding']['graph'] == change['graph'] and
                     curve['origin_binding'].get('layer', 1) == index, 'PLOT_EDIT_CURVE_OUTSIDE_SCOPE')
            pi = curve['origin_binding']['plot_index']
            code = f'range __baihep=[{graph.name}]{index}!{pi};'
            if apply:
                _require(op.lt_exec(code + f'set __baihep -w {pt_to_origin_width_units(values["line_width_pt"])};'),
                         'PLOT_NATIVE_CURVE_WRITE_FAILED')
            _require(op.lt_exec(code + 'get __baihep -w __baihewidth;'), 'PLOT_NATIVE_CURVE_READ_FAILED')
            observed['line_width_pt'] = op.lt_float('__baihewidth') / 500
        else:
            raise GateError('PLOT_NATIVE_EDIT_UNSUPPORTED: 本入口支持文字位置/字号、刻度字号、已绑定曲线线宽；其它修改交专用原生工具。')
        _require(all(math.isclose(observed[k], v, abs_tol=.01, rel_tol=0) for k, v in values.items()),
                 'PLOT_NATIVE_EDIT_READBACK_MISMATCH')
        result.append(dict(change=change, observed=observed))
    _require(result, 'PLOT_NATIVE_EDITS_REQUIRED')
    return result


def revise(task_path, out, reopen=False):
    inspect_plot_task(task_path)
    base = Path(task_path).parent
    task = read(task_path)
    _require(task['operation'] == 'revise_origin', 'PLOT_REVISION_OPERATION_REQUIRED')
    sys.path[:0] = [str(PLOT / 'vendor/editaplot/runtime/src'), str(PLOT / 'scripts'), str(PLOT / 'src')]
    from origin_sciplot.origin_backend.execution_context import require_interactive_origin_context
    from origin_sciplot.origin_backend.job_queue import origin_job_slot
    from origin_sciplot.origin_backend.session import OriginSession
    from origin_sciplot.origin_backend.export_utils import export_graph
    require_interactive_origin_context()
    source = reference(task['parent_origin'], base)
    native = out / '当前可编辑数据图.opju'
    with origin_job_slot(job_kind='baihe-existing-plot-revision'):
        with OriginSession(keep_open=False) as session:
            op = session.op
            _require(op.open(str(native if reopen else source)), 'PLOT_NATIVE_OPEN_FAILED')
            before = _snapshot(op)
            bindings = _bindings(op, task, base)
            if reopen:
                _require(digest(before) == read(out / '修改记录.json')['tables_digest'], 'PLOT_NATIVE_REOPEN_TABLE_MISMATCH')
            changes = _changes(op, task, apply=not reopen)
            _require(digest(before) == digest(_snapshot(op)), 'PLOT_NATIVE_SOURCE_VALUES_CHANGED')
            op.lt_exec('doc -uw;')
            if not reopen:
                _require(op.save(str(native)), 'PLOT_NATIVE_SAVE_FAILED')
            dest = out / ('独立重开' if reopen else '当前图')
            dest.mkdir()
            for i, name in enumerate(dict.fromkeys(b['graph'] for b in bindings), 1):
                graph = op.find_graph(name)
                export_graph(op, graph, dest / f'数据图{i}.png', dest / f'数据图{i}.pdf')
            report = dict(status='NATIVE_REOPENED_PENDING_VISUAL' if reopen else 'NATIVE_REVISED_PENDING_REOPEN',
                          native_bindings=bindings, edits=changes, tables_digest=digest(before), source_sha256=sha(source),
                          visual='NOT_REVIEWED', author_acceptance='NOT_RECORDED')
            save(out / ('重开记录.json' if reopen else '修改记录.json'), report)
            if reopen:
                exports = []
                for i, name in enumerate(dict.fromkeys(b['graph'] for b in bindings), 1):
                    for folder in (out / '当前图', dest):
                        for extension in ('png', 'pdf'):
                            exports.append(dict(sha256=sha(folder / f'数据图{i}.{extension}'), graph_id=name))
                save(out / '原生工程与导出绑定.json', dict(schema_version='native-plot-binding-0.1',
                     project=dict(sha256=sha(native)), exports=exports,
                     arrays=[{k: b[k] for k in ('source_sha256','raw_source_sha256','locator','values_sha256')} for b in bindings],
                     native_readback=dict(status='MATCH', method='origin_native', graph_bindings=bindings),
                     scope='本记录绑定的已反读曲线及导出图；视觉和作者采用另验。'))


if __name__ == '__main__':
    mode, task_file, output = sys.argv[1:4]
    output = writable(output)
    if mode == 'render':
        render(task_file, output)
    elif mode in ('revise', 'reopen'):
        revise(task_file, output, reopen=mode == 'reopen')
    else:
        raise GateError('PLOT_NATIVE_WORKER_MODE_INVALID')
