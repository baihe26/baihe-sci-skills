"""Actual failure classes replayed on neutral arrays, without research data or COM."""
from pathlib import Path
import copy
import csv
import sys
import unittest
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / '工作台/源码'))
from paths import ROOT, read, save, sha
from core import GateError
from plot_sources import audit_curve, check_histogram, presentation_checks, inspect_plot_task, xy_series, energy_kind_from_header
from plot_runtime import prepare_native


class PlotRegressions(unittest.TestCase):
    def setUp(self):
        temp = ROOT / '临时文件'
        temp.mkdir(exist_ok=True, parents=True)
        self.temp = tempfile.TemporaryDirectory(prefix='数据图返工验证_', dir=temp)
        self.base = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.base/'身份.txt').write_text('Synthetic material A; no scientific finding.', encoding='utf-8')
        self.x = [400 + i for i in range(101)]
        self.y = [1 if i != 51 else 20 for i in range(101)]
        self.source = self.csv('原表.csv', self.x, self.y)
        self.display = self.csv('显示表.csv', self.x, self.y)
        self.curve = dict(id='spectrum', group_id='A', display_label='Material A',
                          identity_basis=self.ref('身份.txt'),
                          source=dict(table=self.source, x='Wavenumber', y='Signal'),
                          display=dict(table=self.display, x='Wavenumber', y='Signal'))

    def ref(self, name):
        return dict(path=name, sha256=sha(self.base/name))

    def csv(self, name, x, y):
        with (self.base/name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(['Wavenumber', 'Signal'])
            writer.writerows(zip(x, y))
        return self.ref(name)

    def task(self, **changes):
        task = dict(schema_version='plot-task-1', task_id='synthetic', authorization='Requested neutral test',
                    operation='render_table', plot_type='continuous_spectrum', render_table=self.display,
                    curves=[copy.deepcopy(self.curve)], backend=dict(template_id='ftir', column_mapping=dict(
                        assignments={'Wavenumber': 'x', 'Signal': 'series'}, plot_mode='overlay')))
        task.update(changes)
        save(self.base/'任务.json', task)
        return self.base/'任务.json'

    def test_full_source_array_is_preserved(self):
        report = audit_curve(self.curve, self.base)
        self.assertEqual(report['source']['finite_points'], 101)
        self.assertEqual(report['status'], 'PASS')

    def test_sparse_digitization_does_not_pass_as_full_curve(self):
        self.curve['display']['table'] = self.csv('少点.csv', self.x[::10], self.y[::10])
        with self.assertRaisesRegex(GateError, 'ARRAY_MISMATCH'):
            audit_curve(self.curve, self.base)

    def test_equal_count_wrong_values_still_fails(self):
        self.curve['display']['table'] = self.csv('错列.csv', self.x, [1]*101)
        with self.assertRaisesRegex(GateError, 'ARRAY_MISMATCH'):
            audit_curve(self.curve, self.base)

    def test_nan_and_numeric_errors_are_not_silently_filtered(self):
        self.curve['display']['table'] = self.csv('坏值.csv', self.x, ['nan']+self.y[1:])
        with self.assertRaisesRegex(GateError, 'NONFINITE'):
            audit_curve(self.curve, self.base)

    def test_original_changed_stops(self):
        (self.base/'原表.csv').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(GateError, 'SOURCE_CHANGED'):
            audit_curve(self.curve, self.base)

    def test_missing_segment_stays_a_gap(self):
        gap = self.y[:]
        gap[10] = None
        self.curve['source']['table'] = self.csv('带缺口.csv', self.x, gap)
        self.curve['display']['table'] = self.csv('删缺口.csv', self.x[:10]+self.x[11:], gap[:10]+gap[11:])
        with self.assertRaisesRegex(GateError, 'ARRAY_MISMATCH'):
            audit_curve(self.curve, self.base)

    def test_authorized_sampling_still_cannot_remove_peak(self):
        self.curve['native_full'] = copy.deepcopy(self.curve['source'])
        self.curve['display_sampling'] = dict(reason='display-only', authorization='explicit', indices=list(range(0,101,10)))
        self.curve['display']['table'] = self.csv('抽稀.csv', self.x[::10], self.y[::10])
        with self.assertRaisesRegex(GateError, 'REMOVES_FEATURE'):
            audit_curve(self.curve, self.base)

    def test_authorized_display_sampling_keeps_full_native_and_peak(self):
        indices = sorted({*range(0,101,10), 51})
        self.curve['native_full'] = copy.deepcopy(self.curve['source'])
        self.curve['display_sampling'] = dict(reason='display-only', authorization='explicit', indices=indices)
        self.curve['display']['table'] = self.csv('保峰抽稀.csv', [self.x[i] for i in indices], [self.y[i] for i in indices])
        self.assertIsNotNone(audit_curve(self.curve,self.base)['warning'])

    def test_units_require_actual_scale_and_evidence(self):
        self.curve['y_units'] = {'source':'mg/L', 'display':'microgram/L'}
        with self.assertRaisesRegex(GateError,'UNIT_RELABEL'):
            audit_curve(self.curve,self.base)
        self.curve['transforms'] = [dict(kind='affine',axis='y',scale=1000,offset=0,
                                        reason='Unit conversion',evidence=self.ref('身份.txt'))]
        self.curve['display']['table'] = self.csv('换单位.csv',self.x,[1000*v for v in self.y])
        self.assertEqual(audit_curve(self.curve,self.base)['status'],'PASS')

    def test_energy_title_cannot_change_without_coordinates(self):
        self.curve.update(source_energy_kind='kinetic',display_energy_kind='binding')
        with self.assertRaisesRegex(GateError,'ENERGY_RELABEL'):
            audit_curve(self.curve,self.base)

    def test_energy_conversion_uses_declared_reference_not_assumed_work_function(self):
        self.curve.update(source_energy_kind='kinetic',display_energy_kind='binding')
        self.curve['transforms'] = [dict(kind='energy',source_kind='kinetic',target_kind='binding',
            photon_energy_eV=1486.6,reference_offset_eV=0,reference_basis='Synthetic calibrated analyzer',
            reason='Synthetic reference',evidence=self.ref('身份.txt'))]
        self.curve['display']['table'] = self.csv('换能标.csv',[1486.6-v for v in self.x],self.y)
        self.assertEqual(audit_curve(self.curve,self.base)['status'],'PASS')
        self.curve['transforms'][0].pop('reference_basis')
        with self.assertRaisesRegex(GateError,'ENERGY_REFERENCE'):
            audit_curve(self.curve,self.base)

    def test_histogram_keeps_bins_counts_and_last_edge(self):
        self.assertEqual(check_histogram([0,1,1.5,2],[0,1,2],[1,3])['status'],'PASS')
        with self.assertRaisesRegex(GateError,'HEIGHTS_MISMATCH'):
            check_histogram([0,1,1.5,2],[0,1,2],[2,2])

    def test_dense_spectrum_has_no_every_sample_markers(self):
        self.curve['style'] = dict(sample_markers=True)
        with self.assertRaisesRegex(GateError,'SPECTRUM_SAMPLE_MARKERS'):
            presentation_checks(dict(plot_type='continuous_spectrum',curves=[self.curve]))
        self.assertTrue(presentation_checks(dict(plot_type='discrete_curve',curves=[self.curve])))

    def test_legend_marker_must_match_discrete_curve(self):
        self.curve.update(style=dict(color='#123456',marker='triangle'),legend=dict(color='#123456',marker='circle'))
        with self.assertRaisesRegex(GateError,'LEGEND_SERIES_MISMATCH'):
            presentation_checks(dict(curves=[self.curve]))

    def test_legend_sample_is_not_an_underline(self):
        self.curve['legend'] = dict(sample_center_y=20,text_bounds=[0,10,40,10])
        with self.assertRaisesRegex(GateError,'UNDERLINE_POSITION'):
            presentation_checks(dict(curves=[self.curve]))
        self.curve['legend']['sample_center_y']=15
        self.assertTrue(presentation_checks(dict(curves=[self.curve])))

    def test_unknown_error_definition_is_not_invented(self):
        self.curve['error_column']='sd'
        with self.assertRaisesRegex(GateError,'ERROR_DEFINITION'):
            presentation_checks(dict(curves=[self.curve]))

    def test_source_mapping_check_does_not_claim_native_review(self):
        report=inspect_plot_task(self.task())
        self.assertEqual(report['native_bindings'],'NOT_READ')
        self.assertEqual(report['visual'],'NOT_REVIEWED')

    def test_same_display_source_different_render_file_is_rejected(self):
        second=self.csv('别表.csv',self.x,self.y)
        with self.assertRaisesRegex(GateError,'RENDER_TABLE_BINDING'):
            inspect_plot_task(self.task(render_table=second))

    def test_actual_preparer_accepts_custom_size_and_label_without_data_change(self):
        import plot_runtime
        packaged=REPO/'配套程序/科研绘图工位'
        task_path=self.task(physical_style=dict(page_width_cm=10,page_height_cm=8,
                                               axis_title_size_pt=12,tick_label_size_pt=10,
                                               legend_size_pt=10,plot_line_width_pt=1.2))
        with patch.object(plot_runtime,'PLOT',packaged):
            task,audit,manifest,prepared=prepare_native(task_path)
        self.assertEqual(manifest.id,'ftir')
        self.assertEqual(prepared.plot_spec.series[0].label,'Material A')
        self.assertEqual(prepared.plot_spec.display_plan.figure_style.plot_line_width_pt,1.2)
        self.assertEqual(prepared.plot_spec.display_plan.figure_style.page_width_cm,10)
        self.assertEqual(prepared.source_sha256,self.display['sha256'])

    def test_actual_preparer_rejects_narrow_checked_range_before_full_table_render(self):
        self.curve['source']['rows']=[1,20]
        self.curve['display']['rows']=[1,20]
        with self.assertRaisesRegex(GateError,'TABLE_RANGE_MISMATCH'):
            prepare_native(self.task())

    def test_actual_preparer_does_not_silently_draw_unmapped_columns(self):
        task_path=self.task()
        task=read(task_path)
        task['backend']['column_mapping']['assignments']['Signal']='ignored'
        task_path.unlink();save(task_path,task)
        with self.assertRaises((GateError,ValueError)):
            prepare_native(task_path)

    def test_current_xps_preparation_keeps_kinetic_energy(self):
        with (self.base/'动能.csv').open('w', newline='', encoding='utf-8') as handle:
            w=csv.writer(handle);w.writerow(['Kinetic Energy (E)','Counts / s'])
            w.writerows([(920-i*.1, 100+500*(1-abs(i-20)/20)) for i in range(41)])
        ref=self.ref('动能.csv')
        self.curve['source']=dict(table=ref,x='Kinetic Energy (E)',y='Counts / s')
        self.curve['display']=copy.deepcopy(self.curve['source'])
        self.curve.update(source_energy_kind='kinetic',display_energy_kind='kinetic')
        path=self.task(render_table=ref,backend=dict(template_id='xps',column_mapping=dict(
            x='Kinetic Energy (E)',raw='Counts / s',energy_kind='kinetic',components=[],ignored=[])))
        _,_,_,prep=prepare_native(path)
        self.assertEqual(prep.detection.energy_kind,'kinetic')
        self.assertIn('Kinetic',prep.plot_spec.axis.x_title)

    def test_axis_title_override_is_bound_to_specific_evidence(self):
        path=self.task(axis_titles={'x':dict(title='Wavenumber (cm^-1)',reason='Known acquisition coordinate',
                                            evidence=self.ref('身份.txt'))})
        _,_,_,prep=prepare_native(path)
        self.assertEqual(prep.plot_spec.x_title,'Wavenumber (cm^-1)')

    def error_task(self, include=True):
        for filename in ('原误差表.csv','当前误差表.csv'):
            (self.base/filename).write_text('Time,Signal,Signal SD\n0,20,2\n1,21,2\n2,24,1\n3,25,2\n', encoding='utf-8')
        raw, current=self.ref('原误差表.csv'),self.ref('当前误差表.csv')
        self.curve['source']=dict(table=raw,x='Time',y='Signal')
        self.curve['display']=dict(table=current,x='Time',y='Signal')
        if include:
            self.curve['uncertainty']=dict(definition='SD',evidence=self.ref('身份.txt'),
                source=dict(table=raw,x='Time',y='Signal SD'),display=dict(table=current,x='Time',y='Signal SD'))
        return self.task(render_table=current,plot_type='discrete_curve',backend=dict(template_id='line_error',
            column_mapping=dict(assignments={'Time':'x','Signal':'series','Signal SD':'error'})))

    def test_native_error_role_cannot_escape_evidence_by_omitting_error_field(self):
        with self.assertRaisesRegex(GateError,'NATIVE_ERROR_BINDING_REQUIRED'):
            prepare_native(self.error_task(False))

    def test_actual_error_arrays_and_sd_definition_are_checked(self):
        _,_,_,prep=prepare_native(self.error_task())
        self.assertEqual(prep.plot_spec.series[0].error_kind.lower(),'sd')

    def test_same_count_substituted_error_values_fail(self):
        path=self.error_task()
        t=read(path)
        (self.base/'当前误差表.csv').write_text('Time,Signal,Signal SD\n0,20,8\n1,21,8\n2,24,8\n3,25,8\n', encoding='utf-8')
        t['render_table']=self.ref('当前误差表.csv')
        t['curves'][0]['display']['table']=t['render_table']
        t['curves'][0]['uncertainty']['display']['table']=t['render_table']
        path.unlink();save(path,t)
        with self.assertRaisesRegex(GateError,'ARRAY_MISMATCH'):
            prepare_native(path)

    def test_error_definition_disagrees_with_actual_native_series(self):
        path=self.error_task();t=read(path);t['curves'][0]['uncertainty']['definition']='SEM'
        path.unlink();save(path,t)
        with self.assertRaisesRegex(GateError,'ERROR_DEFINITION_MISMATCH'):
            prepare_native(path)

    def test_error_wrong_column_cannot_be_faked_by_same_values(self):
        path=self.error_task();t=read(path)
        t['curves'][0]['uncertainty']['source']['y']='Signal'
        t['curves'][0]['uncertainty']['display']['y']='Signal'
        path.unlink();save(path,t)
        with self.assertRaisesRegex(GateError,'ERROR_COLUMN_MISMATCH'):
            prepare_native(path)

    def test_kinetic_header_conflict_requires_evidence_not_an_assertion(self):
        (self.base/'带错表头.csv').write_text('Kinetic Energy (eV),Counts\n285,10\n286,20\n287,5\n',encoding='utf-8')
        ref=self.ref('带错表头.csv')
        self.curve['source']=dict(table=ref,x='Kinetic Energy (eV)',y='Counts')
        self.curve['display']=copy.deepcopy(self.curve['source'])
        self.curve.update(source_energy_kind='binding',display_energy_kind='binding')
        with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
            audit_curve(self.curve,self.base)
        correction=dict(header_kind='kinetic',resolved_kind='binding',reason='Synthetic confirmed mislabeled instrument header',
                        evidence=self.ref('身份.txt'))
        self.curve['source_energy_correction']=correction
        self.curve['display_energy_correction']=correction
        self.assertEqual(audit_curve(self.curve,self.base)['status'],'PASS')

    def energy_task(self, source_header, display_header, source_kind, display_kind, converted=False):
        raw_x = [920-i*.5 for i in range(5)]
        display_x = [1486.6-v for v in raw_x] if converted else raw_x
        for filename, header, values in (('原能标.csv',source_header,raw_x),
                                          ('显示能标.csv',display_header,display_x)):
            with (self.base/filename).open('w',newline='',encoding='utf-8') as handle:
                w=csv.writer(handle);w.writerow([header,'Counts']);w.writerows(zip(values,[10,20,30,20,10]))
        self.curve['source']=dict(table=self.ref('原能标.csv'),x=source_header,y='Counts')
        self.curve['display']=dict(table=self.ref('显示能标.csv'),x=display_header,y='Counts')
        self.curve.update(source_energy_kind=source_kind,display_energy_kind=display_kind)
        self.curve.pop('transforms',None)
        if converted:
            self.curve['transforms']=[dict(kind='energy',source_kind=source_kind,target_kind=display_kind,
                photon_energy_eV=1486.6,reference_offset_eV=0,reference_basis='Synthetic calibrated analyzer',
                reason='Synthetic verified coordinate conversion',evidence=self.ref('身份.txt'))]
        path=self.base/'任务.json'
        if path.exists():path.unlink()
        return self.task(render_table=self.ref('显示能标.csv'),backend=dict(template_id='xps',column_mapping=dict(
            x=display_header,raw='Counts',energy_kind=display_kind,components=[],ignored=[])))

    def test_energy_alias_source_conflicts_fail_before_native_preparation(self):
        aliases={'kinetic':['KE','ke (eV)','Kinetic Energy (E)','动能 (eV)','动力学能'],
                 'binding':['BE','bE (eV)','Binding Energy (eV)','结合能 (eV)','束缚能']}
        for actual,names in aliases.items():
            wrong='binding' if actual=='kinetic' else 'kinetic'
            for name in names:
                with self.subTest(header=name):
                    path=self.energy_task(name,'Binding Energy (eV)' if wrong=='binding' else 'Kinetic Energy (eV)',wrong,wrong)
                    with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
                        prepare_native(path)

    def test_energy_alias_display_conflict_also_fails(self):
        for name in ('KE (eV)','动能（eV）','BE (eV)','结合能（eV）'):
            actual='kinetic' if name.startswith(('KE','动能')) else 'binding'
            wrong='binding' if actual=='kinetic' else 'kinetic'
            with self.subTest(header=name):
                path=self.energy_task('Energy (eV)',name,wrong,wrong)
                with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
                    prepare_native(path)

    def test_unknown_energy_headers_are_not_classified_from_numbers_or_substrings(self):
        for name in ('Energy (eV)','X','未命名列','Kerr energy','BEad size','binding affinity','to be processed'):
            with self.subTest(header=name):
                self.assertIsNone(energy_kind_from_header(name))
                path=self.energy_task(name,'Binding Energy (eV)','binding','binding')
                _,_,_,prep=prepare_native(path)
                self.assertEqual(prep.detection.energy_kind,'binding')

    def test_energy_alias_true_coordinate_conversion_passes_actual_preparer(self):
        for source,display in (('KE (eV)','BE (eV)'),('动能（eV）','结合能（eV）'),
                               ('Kinetic Energy (eV) - as acquired','Binding Energy (eV) - calibrated'),
                               ('原始动能/eV','校准后的结合能/eV')):
            with self.subTest(source=source):
                path=self.energy_task(source,display,'kinetic','binding',converted=True)
                _,audit,_,prep=prepare_native(path)
                self.assertEqual(audit['curves'][0]['status'],'PASS')
                self.assertAlmostEqual(prep.plot_spec.axis.source_min_ev,566.6)
                self.assertEqual(prep.detection.energy_kind,'binding')

    def test_energy_alias_header_correction_still_requires_bound_evidence(self):
        for name in ('KE (eV)','动能 (eV)','Kinetic Energy (eV) - as acquired','校准后：KE/eV'):
            with self.subTest(header=name):
                path=self.energy_task(name,'BE (eV)','binding','binding')
                task=read(path)
                task['curves'][0]['source_energy_correction']=dict(header_kind='kinetic',resolved_kind='binding',
                    reason='Synthetic documented mislabeled header',evidence=self.ref('身份.txt'))
                path.unlink();save(path,task)
                _,_,_,prep=prepare_native(path)
                self.assertEqual(prep.detection.energy_kind,'binding')
                task['curves'][0]['source_energy_correction'].pop('evidence')
                path.unlink();save(path,task)
                with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
                    prepare_native(path)

    def test_energy_title_notes_do_not_hide_coordinate_identity(self):
        aliases={
            'kinetic':['Kinetic Energy (eV) - as acquired','Acquired Kinetic Energy (eV)',
                       'Kinetic_Energy_eV - raw','calibrated ke (eV)','原始：KE / eV',
                       'KE - acquisition export','原始动能（eV） - 采集数据','校准后的动力学能/eV'],
            'binding':['Binding Energy (eV) - corrected','Measured BindingEnergy(eV)',
                       'BE / eV - corrected','校准后：be/eV','BE - calibrated',
                       '结合能（eV）- 校准值','校准后的束缚能/eV'],
        }
        for actual,names in aliases.items():
            wrong='binding' if actual=='kinetic' else 'kinetic'
            for name in names:
                with self.subTest(header=name):
                    self.assertEqual(energy_kind_from_header(name),actual)
                    canonical='Binding Energy (eV)' if wrong=='binding' else 'Kinetic Energy (eV)'
                    with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
                        prepare_native(self.energy_task(name,canonical,wrong,wrong))
                    # The display title is checked with the same lexical rules.
                    with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
                        prepare_native(self.energy_task(canonical,name,wrong,wrong))
                    canonical='Binding Energy (eV)' if actual=='binding' else 'Kinetic Energy (eV)'
                    _,_,_,prep=prepare_native(self.energy_task(name,canonical,actual,actual))
                    self.assertEqual(prep.detection.energy_kind,actual)

    def test_header_naming_both_energy_scales_is_not_silently_classified(self):
        for name in ('KE / BE (eV)','Kinetic Energy (eV) - Binding Energy export','动能/结合能（eV）'):
            with self.subTest(header=name):
                self.assertEqual(energy_kind_from_header(name),'ambiguous')
                with self.assertRaisesRegex(GateError,'ENERGY_HEADER_CONFLICT'):
                    prepare_native(self.energy_task(name,'BE (eV)','binding','binding'))

    def test_per_peak_leaders_are_not_silently_ignored(self):
        self.curve['peak_labels']=[dict(x=450,display='450',leader='required'),dict(x=480,display='480',leader='forbidden')]
        with self.assertRaisesRegex(GateError,'ANNOTATION_HANDOFF_REQUIRED'):
            inspect_plot_task(self.task())

    def test_non_project_specific_category_bar_uses_explicit_category_role(self):
        (self.base/'矿物.csv').write_text('Aggregate,Porosity\nGranite,3\nShale,8\nMarble,1\n',encoding='utf-8')
        ref=self.ref('矿物.csv')
        self.curve['source']=dict(table=ref,x='Aggregate',y='Porosity')
        self.curve['display']=copy.deepcopy(self.curve['source'])
        path=self.task(render_table=ref,plot_type='category_bar',backend=dict(template_id='bar',
            column_mapping=dict(assignments={'Aggregate':'category','Porosity':'series'})))
        _,audit,_,prep=prepare_native(path)
        self.assertEqual(audit['curves'][0]['x_type'],'category')
        self.assertEqual(prep.plot_spec.category_column,'Aggregate')
        from origin_sciplot.scientific_workflow import load_scientific_frame
        frame=load_scientific_frame(self.base/'矿物.csv',prep)
        self.assertEqual(frame['Aggregate'].tolist(),['Granite','Shale','Marble'])

    def test_category_reorder_does_not_pass_as_same_curve(self):
        (self.base/'矿物源.csv').write_text('Aggregate,Porosity\nGranite,3\nShale,8\n',encoding='utf-8')
        (self.base/'矿物改.csv').write_text('Aggregate,Porosity\nShale,3\nGranite,8\n',encoding='utf-8')
        self.curve['source']=dict(table=self.ref('矿物源.csv'),x='Aggregate',y='Porosity')
        self.curve['display']=dict(table=self.ref('矿物改.csv'),x='Aggregate',y='Porosity')
        self.curve['x_type']='category'
        with self.assertRaisesRegex(GateError,'ARRAY_MISMATCH'):
            audit_curve(self.curve,self.base)

    def test_explicit_per_series_style_is_not_acknowledged_without_application(self):
        self.curve['style']=dict(color='#ff0000',line_width=2)
        with self.assertRaisesRegex(GateError,'SERIES_STYLE_HANDOFF_REQUIRED'):
            prepare_native(self.task())

    def test_existing_origin_source_rejects_another_manual_parent(self):
        from task_context import load_context
        import os
        (self.base/'current.opju').write_bytes(b'synthetic current parent')
        (self.base/'old.opju').write_bytes(b'synthetic old parent')
        self.curve['origin_binding']=dict(graph='Graph1',worksheet='[Book1]1',x_column='A',y_column='B',rows=[1,101])
        path=self.task(operation='revise_origin',parent_origin=self.ref('old.opju'))
        context=dict(schema_version='task-context-0.1',project_id='neutral',stage='revise',
                     parent=self.ref('current.opju'))
        save(self.base/'上下文.json',context)
        with patch.dict(os.environ,{'BAIHE_SCI_TASK_CONTEXT':str(self.base/'上下文.json')}):
            with self.assertRaisesRegex(ValueError,'NOT_ADOPTED_PARENT'):
                inspect_plot_task(path)


if __name__=='__main__':
    unittest.main()
