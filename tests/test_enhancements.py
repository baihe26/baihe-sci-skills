"""Known-bad scientific contracts and cooperative editing boundaries."""
from pathlib import Path
import sys, unittest, copy, uuid
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'工作台/源码'))
from paths import ROOT, read, sha
from core import GateError
from scientific_gate import validate_design, validate_scene, validate_pack
from processing_ledger import from_scene, validate_ledger, bounded_review
from coordination import append_checkpoint, exclusive, single_writer
from native_connectors import rectangle_connector_plan


class EnhancementTests(unittest.TestCase):
    def setUp(self):
        self.base = REPO/'示例/简单科学关系'
        self.spec, self.plan, self.binding, self.graph = (read(self.base/name) for name in
            ('FigureSpec.json', 'ConstructionPlan.json', 'scientific_binding.json', 'IllustratorSceneGraph.json'))

    def valid(self):
        return validate_design(self.spec, self.plan, self.binding, self.base, self.base)

    def test_existing_pack_passes(self):
        self.assertEqual(validate_pack(self.base/'IllustratorSceneGraph.json')['scene']['status'], 'PASS')

    def test_only_exact_rectangle_connectors(self):
        plans = rectangle_connector_plan(self.graph)
        self.assertEqual(set(plans), {'AI_R1'})
        self.assertEqual(plans['AI_R1']['source'], dict(object_id='AI_box_A', site=4))
        self.graph['arrow_objects'][0]['geometry']['data']['points'][0][1] += 1
        self.assertEqual(rectangle_connector_plan(self.graph), {})

    def test_binding_mutants_rejected(self):
        for key, value in [('source', 'fig_B'), ('target', 'fig_A'), ('certainty', 'HYPOTHESIZED'),
                           ('claim_id', 'C2'), ('direction', 'reverse'), ('negated', True),
                           ('relation_type', 'inhibition'), ('visual_encoding', 'dashed_arrow')]:
            with self.subTest(key=key):
                self.binding = read(self.base/'scientific_binding.json')
                self.binding['relations'][0][key] = value
                with self.assertRaises(GateError): self.valid()

    def test_claim_source_and_identity_mutants(self):
        for change in ('source_hash', 'input_hash', 'text', 'claim', 'source_ref', 'instance', 'duplicate'):
            self.setUp()
            with self.subTest(change=change):
                if change == 'source_hash': self.binding['source_file']['sha256'] = '0'*64
                elif change == 'input_hash': self.spec['metadata']['input_sha256'] = '0'*64
                elif change == 'text': self.spec['metadata']['input_text'] += 'Changed'
                elif change == 'claim': self.binding['claims'][0]['statement'] = 'reversed'
                elif change == 'source_ref':
                    self.spec['scientific_claims'][0]['supporting_source_ids'] = ['MISSING']
                    self.binding['claims'] = copy.deepcopy(self.spec['scientific_claims'])
                elif change == 'instance': self.plan['instances'][0]['entity_id'] = 'E_B'
                else: self.binding['claims'].append(copy.deepcopy(self.binding['claims'][0]))
                with self.assertRaises(GateError): self.valid()

    def test_plan_and_scene_mutants(self):
        for change in ('direction', 'certainty', 'negation', 'claim', 'route', 'scene_host', 'scene_encoding', 'scene_text'):
            self.setUp()
            with self.subTest(change=change), self.assertRaises(GateError):
                if change == 'direction': self.plan['relations'][0]['source'] = 'fig_B'
                elif change == 'certainty': self.plan['relations'][1]['epistemic_status'] = 'DIRECTLY_SUPPORTED'
                elif change == 'negation': self.plan['relations'][0]['negated'] = True
                elif change == 'claim': self.plan['relations'][0]['claim_ids'] = ['C2']
                elif change == 'route': self.plan['relations'][0]['points'][0][0] += 10
                elif change == 'scene_host': self.graph['arrow_objects'][0]['source_id'] = 'AI_fig_B'
                elif change == 'scene_encoding': self.graph['arrow_objects'][1]['geometry']['data']['encoding'] = 'solid_arrow'
                else: self.graph['text_objects'][0]['geometry']['data']['text'] = 'Changed label'
                self.valid(); validate_scene(self.spec, self.plan, self.graph)

    def test_processing_ledger_coverage_and_fake_native(self):
        ledger = from_scene(self.graph)
        self.assertEqual(ledger['check']['accounted'], 10)
        ledger['elements'].pop()
        with self.assertRaises(GateError): validate_ledger(ledger)
        for bad in ('false_native', 'semantic_crop', 'uncertain_approved'):
            ledger = from_scene(self.graph); row = ledger['elements'][0]
            row.update(treatment='retained_pixels', editability='MOVE_SCALE_REPLACE', source_sha256='a'*64,
                       content_kind='scientific_image', crop_box_normalized=[0, 0, 1, 1])
            if bad == 'false_native': row['editability'] = 'FULL_NATIVE'
            elif bad == 'semantic_crop': row['content_kind'] = 'mechanism_arrow'
            else: row.update(uncertain=True, review_status='APPROVED')
            with self.subTest(bad=bad), self.assertRaises(GateError): validate_ledger(ledger)
        # A real photograph may be retained; it is never counted as native geometry.
        ledger['elements'] = [dict(id='photo', source_ref='source-image', output_ids=['photo'],
            treatment='retained_pixels', editability='MOVE_SCALE_REPLACE', source_sha256='a'*64,
            content_kind='scientific_image', uncertain=False, review_status='PENDING')]
        ledger['required_ids'] = ['photo']; ledger['native_required_ids'] = []
        self.assertEqual(validate_ledger(ledger)['native_count'], 0)

    def test_bounded_review_stops(self):
        self.assertEqual(bounded_review([])['status'], 'NOT_REVIEWED')
        self.assertEqual(bounded_review([dict(unresolved_issue_ids=['A']), dict(unresolved_issue_ids=['A'])])['status'], 'STOP_NO_STRICT_PROGRESS')
        self.assertEqual(bounded_review([dict(unresolved_issue_ids=['A','B']), dict(unresolved_issue_ids=['A'])])['status'], 'STOP_BUDGET')
        self.assertEqual(bounded_review([dict(unresolved_issue_ids=[])])['status'], 'PASS_RECORDED_SCOPE')

    def test_checkpoint_conflicts_and_input_changes(self):
        folder = ROOT/'临时文件'/('交接测试_'+uuid.uuid4().hex)
        src = folder/'source.txt'; src.parent.mkdir(parents=True); src.write_text('original', encoding='utf-8')
        first = append_checkpoint(folder, 'INPUT_BOUND', [src], None, 'a'*64, 'reader')
        with self.assertRaises(GateError): append_checkpoint(folder, 'DESIGN_READY', [src], None, 'a'*64, 'designer')
        second = append_checkpoint(folder, 'DESIGN_READY', [src], first['sha256'], 'a'*64, 'designer')
        src.write_text('changed', encoding='utf-8')
        with self.assertRaises(GateError): append_checkpoint(folder, 'NATIVE_RECORDED', [src], second['sha256'], 'a'*64, 'producer')

    def test_exclusive_writer(self):
        from paths import DESKTOP_LOCKS
        if any(p.exists() for p in DESKTOP_LOCKS): self.skipTest('another native task owns the desktop')
        @single_writer
        def nested():
            @single_writer
            def conflicting(): return True
            with self.assertRaises(GateError): conflicting()
        nested()
        self.assertFalse((ROOT/'桌面生产.lock').exists())

    def test_handoff_history_tamper_rejected(self):
        import json
        folder = ROOT/'临时文件'/('历史测试_'+uuid.uuid4().hex)
        first = append_checkpoint(folder, 'INPUT_BOUND', [], None, 'a'*64, 'reader')
        second = append_checkpoint(folder, 'DESIGN_READY', [], first['sha256'], 'a'*64, 'designer')
        path = Path(first['path']); row = read(path); row['writer'] = 'tampered'
        path.write_text(json.dumps(row), encoding='utf-8')
        with self.assertRaises(GateError): append_checkpoint(folder, 'NATIVE_RECORDED', [], second['sha256'], 'a'*64, 'producer')


if __name__ == '__main__': unittest.main()
