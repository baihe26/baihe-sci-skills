"""De-identified regressions from repeated real figure-editing failures."""
from pathlib import Path
import copy
import json
import shutil
import sys
import tempfile
import unittest
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from core import GateError
from paths import ROOT,read,sha,save
from preflight import inspect_pack
from refinement import revise
from scientific_gate import validate_design,validate_pack
from design_styles import apply_plan_styles,schema_projection,capability_route


class DesignRegressions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='示意图回归_',dir=ROOT/'临时文件')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/'父本'
        shutil.copytree(REPO/'示例/简单科学关系',self.base)
        self.scene=self.base/'IllustratorSceneGraph.json'

    def write(self,path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

    def request(self,scene,changes,number=0,extra=None,findings=None):
        folder=self.root/('请求'+str(number));folder.mkdir()
        ids=[c['object_id'] for c in changes]
        review=dict(artifact_scene_sha256=sha(scene),reviewer='Independent synthetic reviewer',
                    findings=findings or [dict(id='LABEL',object_ids=ids)])
        save(folder/'审阅.json',review)
        request=dict(expected_parent_sha256=sha(scene),expected_pack_sha256=inspect_pack(scene)['input_fingerprint'],
                     review=dict(path='审阅.json',sha256=sha(folder/'审阅.json')),finding_ids=[review['findings'][0]['id']],
                     allowed_object_ids=ids,changes=changes,**(extra or {}))
        save(folder/'修改.json',request);return folder/'修改.json'

    def test_move_label_changes_coordinates_not_chemistry_or_other_labels(self):
        before=read(self.scene);original_hash=sha(self.scene)
        req=self.request(self.scene,[dict(object_id='AI_text_A',fields=dict(translate_px=[0,8]))])
        report=revise(self.scene,req,self.root/'改后');after=read(self.root/'改后/IllustratorSceneGraph.json')
        a=next(o for o in after['text_objects'] if o['id']=='AI_text_A')
        b=next(o for o in before['text_objects'] if o['id']=='AI_text_A')
        self.assertEqual(a['geometry']['data']['y'],b['geometry']['data']['y']+8)
        self.assertEqual(a['geometry']['data']['text'],b['geometry']['data']['text'])
        self.assertEqual(after['arrow_objects'],before['arrow_objects'])
        self.assertEqual(sha(self.scene),original_hash);self.assertTrue(report['geometry_changed'])
        self.assertEqual(sha(self.root/'改后/scientific_binding.json'),sha(self.base/'scientific_binding.json'))

    def test_reroute_arrow_keeps_source_target_and_binding(self):
        old=read(self.scene);arrow=old['arrow_objects'][0]
        req=self.request(self.scene,[dict(object_id=arrow['id'],fields=dict(points_px=[[320,220],[550,230],[580,220]]))])
        revise(self.scene,req,self.root/'改后')
        path=self.root/'改后/IllustratorSceneGraph.json';validate_pack(path)
        new=read(path)['arrow_objects'][0]
        for key in ('source_id','target_id','relation_id','epistemic_status','scientific_refs'):
            self.assertEqual(new[key],arrow[key])
        self.assertEqual(read(self.root/'改后/ConstructionPlan.json')['relations'][0]['points'],new['geometry']['data']['points'])

    def test_same_relation_id_cannot_point_at_other_material(self):
        req=self.request(self.scene,[dict(object_id='AI_R1',fields=dict(points_px=[[320,220],[450,220],[200,220]]))])
        with self.assertRaisesRegex(GateError,'ENDPOINT_OWNER_CONFLICT'):revise(self.scene,req,self.root/'错误指向')
        self.assertFalse((self.root/'错误指向').exists())

    def test_new_findings_and_more_than_five_rounds_do_not_lose_authorization(self):
        scene=self.scene
        for i in range(7):
            changes=[dict(object_id='AI_text_A',fields=dict(translate_px=[0,1]))]
            req=self.request(scene,changes,i,findings=[dict(id='VISIBLE_'+str(i),object_ids=['AI_text_A'])])
            dest=self.root/('版本'+str(i));result=revise(scene,req,dest);scene=dest/'IllustratorSceneGraph.json'
        self.assertEqual(result['completed_rounds'],7);self.assertIsNone(result['max_rounds'])
        self.assertEqual(result['next_review'],'PENDING')

    def test_explicit_budget_and_actual_noop_remain_guarded(self):
        req=self.request(self.scene,[dict(object_id='AI_text_A',fields=dict(translate_px=[0,0]))])
        with self.assertRaisesRegex(GateError,'NO_ACTUAL_CHANGE'):revise(self.scene,req,self.root/'nope')
        req=self.request(self.scene,[dict(object_id='AI_text_A',fields=dict(translate_px=[0,1]))],1,dict(max_rounds=1))
        revise(self.scene,req,self.root/'first');scene=self.root/'first/IllustratorSceneGraph.json'
        req=self.request(scene,[dict(object_id='AI_text_A',fields=dict(translate_px=[0,1]))],2)
        with self.assertRaisesRegex(GateError,'BUDGET_EXHAUSTED'):revise(scene,req,self.root/'second')

    def test_working_model_can_use_solid_arrow_only_with_real_disclosure(self):
        spec=read(self.base/'FigureSpec.json');plan=read(self.base/'ConstructionPlan.json');binding=read(self.base/'scientific_binding.json')
        rel=spec['relationships'][1];rel['visual_encoding']='solid_arrow'
        binding['relations'][1]['visual_encoding']='solid_arrow'
        next(r for r in spec['routes'] if r['relationship_id']==rel['id'])['encoding']='solid_arrow'
        next(r for r in plan['relations'] if r['relation_id']==rel['id'])['encoding']='solid_arrow'
        with self.assertRaisesRegex(GateError,'HYPOTHESIS_UPGRADED'):validate_design(spec,plan,binding,self.base,self.base)
        label=next(e for e in plan['elements'] if e['id']=='hyp')
        binding['certainty_disclosures']=[dict(relation_ids=[rel['id']],evidence_level='HYPOTHESIZED',
                                             location='legend',object_id='AI_hyp',text=label['data']['text'])]
        self.assertEqual(validate_design(spec,plan,binding,self.base,self.base)['status'],'PASS')
        graph=read(self.scene);apply_plan_styles(plan,graph)
        self.assertIsNone(graph['arrow_objects'][1]['geometry']['data']['dash'])
        binding['certainty_disclosures'][0]['evidence_level']='DIRECTLY_SUPPORTED'
        with self.assertRaisesRegex(GateError,'DISCLOSURE_CERTAINTY_CONFLICT'):validate_design(spec,plan,binding,self.base,self.base)

    def test_caption_disclosure_is_hash_bound_and_in_dependencies(self):
        from pack_files import dependency_paths
        binding=read(self.base/'scientific_binding.json')
        caption=self.base/'图注.txt';caption.write_text('A proposed working model explains the supplied connections.',encoding='utf-8')
        binding['certainty_disclosures']=[dict(relation_ids=['R2'],evidence_level='HYPOTHESIZED',location='caption_file',
            source=dict(path=caption.name,sha256=sha(caption)),text=caption.read_text())]
        self.write(self.base/'scientific_binding.json',binding)
        self.assertIn(caption,dependency_paths(self.scene));validate_pack(self.scene)
        caption.write_text('Edited unrelated statement',encoding='utf-8')
        with self.assertRaisesRegex(GateError,'CAPTION_CHANGED'):validate_pack(self.scene)

    def test_colour_role_reencoding_requires_all_legend_targets(self):
        graph=read(self.scene);obj=graph['objects'][0];old=graph['style_tokens'][obj['style_token']]['fill']
        # A second box is a synthetic swatch with the same material role.
        other=graph['objects'][1];graph['style_tokens'][other['style_token']]['fill']=old
        plan=read(self.base/'ConstructionPlan.json');next(e for e in plan['elements'] if e['id']=='box_B')['fill']=old
        self.write(self.scene,graph);self.write(self.base/'ConstructionPlan.json',plan)
        roles=dict(schema_version='color-roles-0.1',bindings=[dict(object_id=obj['id'],field='fill',kind='scientific',
            role='material_A',value=old,reason='Synthetic material identity',legend_object_ids=[other['id']])])
        self.write(self.base/'color_roles.json',roles)
        rules=dict(color_reencoding=[dict(role='material_A',scope='current_scene',authorization='Author requested one consistent palette remap.',**{'from':old,'to':'#255FC7'})])
        req=self.request(self.scene,[dict(object_id=obj['id'],fields=dict(fill='#255FC7'))],extra=rules)
        with self.assertRaisesRegex(GateError,'INCOMPLETE_LEGEND'):revise(self.scene,req,self.root/'bad')
        req=self.request(self.scene,[dict(object_id=i,fields=dict(fill='#255FC7')) for i in (obj['id'],other['id'])],1,rules)
        report=revise(self.scene,req,self.root/'good');validate_pack(self.root/'good/IllustratorSceneGraph.json')
        self.assertEqual(report['color_scope'],'AUTHORIZED_SCENE_ROLE_REENCODING')
        self.assertEqual(read(self.base/'color_roles.json'),roles)

    def test_gradients_and_transparency_survive_svg_and_saved_pptx(self):
        from vector_adapter import scene_svg
        from portable_ppt import produce
        import xml.etree.ElementTree as ET
        plan=read(self.base/'ConstructionPlan.json');graph=read(self.scene)
        for identity,kind in [('box_A','linear'),('box_B','radial')]:
            element=next(e for e in plan['elements'] if e['id']==identity)
            element['opacity']=.65;element['fill_gradient']=dict(kind=kind,stops=[dict(offset=0,color='#EFFAFF'),dict(offset=1,color='#237795')])
        apply_plan_styles(plan,graph);self.write(self.scene,graph);self.write(self.base/'ConstructionPlan.json',plan)
        validate_pack(self.scene)
        svg=scene_svg(graph);self.assertIn('linearGradient',svg);self.assertIn('radialGradient',svg);self.assertIn('opacity="0.65"',svg)
        report=produce(self.scene,self.root/'ppt')
        with zipfile.ZipFile(report['file']['path']) as z:
            xml=ET.fromstring(z.read('ppt/slides/slide1.xml'));ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
            self.assertEqual(len(xml.findall('.//a:gradFill',ns)),2)
            self.assertTrue(any(v.attrib['val']=='65000' for v in xml.findall('.//a:alpha',ns)))
        self.assertEqual(report['office_native_reopen'],'NOT_PERFORMED_BY_THIS_BACKEND')

    def test_backend_route_never_silently_flattens_unsupported_effects(self):
        graph=read(self.scene);graph['objects'][0]['geometry']['kind']='PATH'
        route=capability_route(graph,'portable')
        self.assertEqual(route['status'],'EXPLICIT_HANDOFF_REQUIRED');self.assertIn('illustrator',route['alternatives'])
        self.assertFalse(route['automatic_flattening'])
        graph['style_tokens'][graph['objects'][0]['style_token']]['fill_gradient']=dict(kind='linear',stops=[dict(offset=0,color='#FFFFFF'),dict(offset=1,color='#005566')])
        self.assertNotIn('fill_gradient',schema_projection(graph)['style_tokens'][graph['objects'][0]['style_token']])
        graph['style_tokens'][graph['objects'][0]['style_token']]['unknown_style']=True
        self.assertIn('unknown_style',schema_projection(graph)['style_tokens'][graph['objects'][0]['style_token']])

    def test_curved_fibre_remains_bezier_control_points_in_ppt(self):
        from vector_paths import path_commands,draw_path
        from portable_ppt import draw_scene
        from pptx import Presentation
        graph=read(self.scene);obj=graph['objects'][0]
        obj['geometry']=dict(kind='PATH',data=dict(d='M 100 220 C 150 170 240 270 300 220',dash=None))
        self.assertIn('portable',capability_route(graph,'portable')['alternatives'])
        prs=Presentation();checked=inspect_pack(self.scene)
        slide,shapes,plans=draw_scene(prs,graph,checked,self.scene)
        self.assertIn('cubicBezTo',shapes[obj['id']].element.xml)
        with self.assertRaisesRegex(GateError,'COMMAND_REQUIRES_ILLUSTRATOR'):path_commands('M 0 0 A 10 10 0 0 1 20 20')

    def test_missing_gradient_renderer_does_not_emit_a_black_fallback(self):
        from design_preview import raster_svg
        from unittest.mock import patch
        svg='<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g"/></defs></svg>'
        with patch('design_preview.browser_executable',return_value=None):
            result=raster_svg(svg,self.root/'不应生成.png',100,100)
        self.assertEqual(result['status'],'COMPATIBLE_RENDERER_REQUIRED');self.assertFalse((self.root/'不应生成.png').exists())
        with self.assertRaisesRegex(GateError,'EXTERNAL_REFERENCE'):
            raster_svg('<svg><image href="https://invalid.example/private.png"/></svg>',self.root/'不可外传.png',100,100)


if __name__=='__main__':unittest.main()
