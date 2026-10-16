"""Functional upgrade checks, including bad crops, unknown text, scoped revisions and real PPTX output."""
from pathlib import Path
import sys,unittest,copy,json,uuid,shutil,zipfile,hashlib,subprocess,os
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from paths import ROOT,read,save,sha,digest
from core import GateError,new_task
from preflight import inspect_pack
from asset_contract import check_assets,check_reconstruction,union_area
from evidence_adapter import check_evidence
from layout_checks import check_layout
from scientific_gate import validate_pack
from refinement import revise
from task_status import status
from qa_report import compare_images


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.base=REPO/'示例/混合重建';self.scene=self.base/'IllustratorSceneGraph.json'
        self.graph=read(self.scene);self.spec=read(self.base/'FigureSpec.json')
        self.assets=read(self.base/'retained_assets.json');self.mapping=read(self.base/'reconstruction_map.json')

    def temp(self):
        p=ROOT/'临时文件'/('升级测试_'+uuid.uuid4().hex);p.mkdir(parents=True);return p

    def test_existing_contract_and_optional_extensions(self):
        report=inspect_pack(self.scene)
        self.assertEqual(report['status'],'PASS_WITH_UNRESOLVED_REVIEW')
        self.assertEqual(report['reconstruction']['uncertain_ids'],['source_unclear_note'])
        self.assertFalse(report['evidence']['automatic_adoption'])
        self.assertEqual(report['evidence']['unresolved_links'][0]['relation'],'limits')
        self.assertEqual(report['layout']['status'],'PASS')

    def test_multiple_crop_union(self):
        self.assertEqual(union_area([[0,0,60,100],[40,0,100,100]]),10000)
        self.assertEqual(union_area([[0,0,20,20],[10,10,30,30]]),700)
        self.assertEqual(union_area([]),0)

    def test_asset_mutants(self):
        for change in ('hash','stretch','dimensions','native','format_box','parent'):
            obj=copy.deepcopy(self.assets);row=obj['assets'][0]
            if change=='hash':row['source']['sha256']='0'*64
            elif change=='stretch':row['bbox'][2]+=25
            elif change=='dimensions':row['source']['size_px']=[900,501]
            elif change=='native':row['editability']='FULL_NATIVE'
            elif change=='format_box':row['source_box_px']=[360,245,9000,345]
            else:row['group_id']='missing'
            with self.subTest(change=change),self.assertRaises(GateError):check_assets(obj,self.base,self.graph)

    def test_mosaic_false_native_rejected(self):
        obj=copy.deepcopy(self.assets);first=obj['assets'][0];first.update(id='crop_left',source_box_px=[0,0,450,500],bbox=[0,0,450,500])
        second=copy.deepcopy(first);second.update(id='crop_right',source_box_px=[450,0,900,500],bbox=[450,0,900,500]);obj['assets'].append(second)
        checked=check_assets(obj,self.base,self.graph)
        self.assertEqual(checked['source_union_coverage'][0]['union_coverage'],1)
        with self.assertRaisesRegex(GateError,'RASTER_COVERS_REQUIRED_NATIVE_REGION'):check_reconstruction(self.mapping,self.base,self.graph,checked)

    def test_retained_crop_cannot_hide_required_output(self):
        obj=copy.deepcopy(self.assets);obj['assets'][0].update(bbox=[100,170,280,270],z_order=100)
        checked=check_assets(obj,self.base,self.graph)
        with self.assertRaisesRegex(GateError,'RASTER_OCCLUDES_REQUIRED_OUTPUT'):check_reconstruction(self.mapping,self.base,self.graph,checked)

    def test_unknown_text_not_guessed_and_regions_accounted(self):
        checked=check_assets(self.assets,self.base,self.graph)
        for bad in ('guessed','approved','missing','raster_output'):
            obj=copy.deepcopy(self.mapping)
            if bad=='guessed':obj['elements'][-1]['resolved_text']='guessed word'
            elif bad=='approved':obj['elements'][-1]['review_status']='APPROVED'
            elif bad=='missing':obj['elements'].pop()
            else:obj['elements'][0]['output_ids']=['texture_inset']
            with self.subTest(bad=bad),self.assertRaises(GateError):check_reconstruction(obj,self.base,self.graph,checked)

    def test_evidence_wrong_quote_links_and_confirmation(self):
        evidence=read(self.base/'evidence_map.json')
        for bad in ('quote','claim','evidence','adoption'):
            obj=copy.deepcopy(evidence)
            if bad=='quote':obj['source_blocks'][0]['quote']='not present'
            elif bad=='claim':obj['claims'][0]['id']='NOT_A_CLAIM'
            elif bad=='evidence':obj['claims'][0]['links'][0]['evidence_id']='missing'
            else:obj['decisions']=[dict(id='D1',status='CONFIRMED')]
            with self.subTest(bad=bad),self.assertRaises(GateError):check_evidence(obj,self.base,self.spec)

    def test_layout_constraints_fail_without_rearranging(self):
        before=copy.deepcopy(self.graph)
        report=check_layout(self.graph,dict(constraints=[dict(id='bad_gap',kind='min_gap',object_ids=['AI_fig_A','AI_fig_B'],minimum_px=400)]))
        self.assertEqual(report['status'],'FAIL');self.assertEqual(self.graph,before)
        for bad in ('parent','scale','duplicate'):
            graph=copy.deepcopy(self.graph)
            if bad=='parent':graph['parent_child'][0]['parent_id']='AI_fig_B'
            elif bad=='scale':graph['geometry']['coordinate_transform']['scale_pt_per_px']*=2
            else:graph['text_objects'][0]['id']=graph['objects'][0]['id']
            from scientific_gate import validate_scene
            with self.subTest(bad=bad),self.assertRaises(GateError):validate_scene(self.spec,read(self.base/'ConstructionPlan.json'),graph)

    def patch_request(self,folder,scene,findings=None,fields=None):
        review=dict(artifact_scene_sha256=sha(scene),reviewer='SYNTHETIC_HOST_REVIEW',findings=findings or [dict(id='F1',object_ids=['AI_text_A'],category='display',description='increase contrast')])
        save(folder/'review.json',review)
        request=dict(expected_parent_sha256=sha(scene),expected_pack_sha256=inspect_pack(scene)['input_fingerprint'],review=dict(path='review.json',sha256=sha(folder/'review.json')),finding_ids=[review['findings'][0]['id']],allowed_object_ids=['AI_text_A'],changes=[dict(object_id='AI_text_A',fields=fields or dict(fill='#102030'))])
        save(folder/'request.json',request);return folder/'request.json'

    def test_actual_style_revision_and_parent_protection(self):
        folder=self.temp();request=self.patch_request(folder,self.scene);before={p.name:sha(p) for p in self.base.iterdir() if p.is_file()}
        result=revise(self.scene,request,folder/'new');self.assertFalse(result['scientific_content_changed'])
        self.assertEqual(sha(folder/'new/FigureSpec.json'),sha(self.base/'FigureSpec.json'))
        self.assertEqual(sha(folder/'new/scientific_binding.json'),sha(self.base/'scientific_binding.json'))
        self.assertEqual(result['changed_object_ids'],['AI_text_A']);validate_pack(folder/'new/IllustratorSceneGraph.json')
        old=read(self.scene);new=read(folder/'new/IllustratorSceneGraph.json')
        for key in ('objects','arrow_objects','groups'):self.assertEqual(old[key],new[key])
        for row in old['text_objects']:
            if row['id']!='AI_text_A':self.assertIn(row,new['text_objects'])
        self.assertEqual(before,{p.name:sha(p) for p in self.base.iterdir() if p.is_file()})
        second=self.temp();r2=self.patch_request(second,folder/'new/IllustratorSceneGraph.json')
        with self.assertRaisesRegex(GateError,'NO_STRICT_PROGRESS'):revise(folder/'new/IllustratorSceneGraph.json',r2,second/'blocked')

    def test_revision_rejects_text_change_and_manual_parent_change(self):
        for bad in ('text','parent','scope','duplicate'):
            folder=self.temp();request=self.patch_request(folder,self.scene,fields=dict(text='wrong') if bad=='text' else None)
            data=read(request)
            if bad=='parent':data['expected_parent_sha256']='0'*64
            elif bad=='scope':data['allowed_object_ids']=['AI_text_B']
            elif bad=='duplicate':data['changes'].append(copy.deepcopy(data['changes'][0]))
            request.write_text(json.dumps(data),encoding='utf-8')
            with self.subTest(bad=bad),self.assertRaises(GateError):revise(self.scene,request,folder/'blocked')

    def test_revision_binds_entire_input_pack(self):
        folder=self.temp();cloned=folder/'source';shutil.copytree(self.base,cloned);scene=cloned/'IllustratorSceneGraph.json'
        request=self.patch_request(folder,scene)
        evidence=read(cloned/'evidence_map.json');evidence['decisions']=[dict(id='D1',status='PROPOSED')]
        (cloned/'evidence_map.json').write_text(json.dumps(evidence),encoding='utf-8')
        with self.assertRaisesRegex(GateError,'INPUT_PACK_CONFLICT'):revise(scene,request,folder/'blocked')

    def test_portable_ppt_contains_native_objects_and_original_image(self):
        from portable_ppt import produce
        folder=self.temp();report=produce(self.scene,folder/'ppt')
        self.assertTrue(report['generated_without_office']);self.assertEqual(report['office_native_reopen'],'NOT_PERFORMED_BY_THIS_BACKEND')
        with zipfile.ZipFile(report['file']['path']) as z:
            hashes={hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if name.startswith('ppt/media/')}
            self.assertIn(sha(self.base/'合成原图.png'),hashes)
            xml=z.read('ppt/slides/slide1.xml').decode('utf-8')
            self.assertIn('stCxn',xml);self.assertIn('endCxn',xml);self.assertIn('Module A',xml);self.assertIn('srcRect',xml)
            import xml.etree.ElementTree as ET
            refs=ET.fromstring(xml).findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}effectRef')
            self.assertTrue(all(ref.get('idx')=='0' for ref in refs))
        ledger=read(folder/'ppt/元素处理清单.json')
        self.assertEqual(ledger['check']['retained_pixel_count'],1)
        self.assertEqual(ledger['check']['omitted_pending_review_count'],1)

    def test_compare_pixels_environment_and_differences(self):
        from PIL import Image
        folder=self.temp();a=folder/'a.png';b=folder/'b.png';Image.new('RGB',(20,20),'white').save(a);shutil.copy2(a,b)
        env=dict(renderer='TEST_FIXTURE',version='1',font_fingerprint='synthetic',resolution_px=[20,20]);save(folder/'env.json',env)
        equal=compare_images(a,b,folder/'same',folder/'env.json',folder/'env.json');self.assertEqual(equal['status'],'EXACT_PIXELS_EQUAL')
        image=Image.open(b);image.putpixel((1,2),(0,0,0));image.save(b)
        diff=compare_images(a,b,folder/'diff',folder/'env.json',folder/'env.json');self.assertEqual(diff['different_pixels'],1);self.assertTrue((folder/'diff/查看差异.html').is_file())
        unmatched=compare_images(a,b,folder/'unknown');self.assertEqual(unmatched['status'],'INCOMPARABLE_ENVIRONMENT')

    def test_status_protects_sources_outputs_and_unknown_writes(self):
        from recovery_journal import Journal
        folder=self.temp();input_path=folder/'input.txt';input_path.write_text('original',encoding='utf-8')
        key='升级状态_'+uuid.uuid4().hex;state=new_task('只作图','SYNTHETIC_TEST',[input_path],key);task=ROOT/'任务'/key
        journal=Journal(task/'恢复日志.jsonl',digest(state));token=journal.begin('one',dict(id='native'))
        self.assertEqual(status(key)['status'],'OUTCOME_UNKNOWN_RECONCILE_FIRST');self.assertFalse(status(key)['automatic_retry'])
        journal.commit(token,1);output=folder/'result.txt';output.write_text('generated',encoding='utf-8')
        save(task/'执行回执.json',dict(output_manifest=[dict(path=str(output),sha256=sha(output))]))
        self.assertEqual(status(key)['status'],'RECORDED_NO_REPLAY')
        output.write_text('manual change',encoding='utf-8');self.assertEqual(status(key)['status'],'OUTPUT_CHANGED_REVIEW_REQUIRED')
        input_path.write_text('new source',encoding='utf-8');self.assertEqual(status(key)['status'],'SOURCE_CONFLICT')

    def test_portable_cli_without_private_engines(self):
        folder=self.temp();env=dict(os.environ,BAIHE_SCI_CONFIG=str(folder/'absent.json'),PYTHONUTF8='1')
        key='无引擎_'+uuid.uuid4().hex
        result=subprocess.run([sys.executable,str(REPO/'工作台/源码/workbench.py'),'--module','vector','--target','ppt','--backend','portable','--scene',str(self.scene),'--out',str(folder/'ppt'),'--request-id',key],env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(status(key)['status'],'RECORDED_NO_REPLAY')
        self.assertEqual(len(list((ROOT/'任务'/key/'交接').glob('交接_*.json'))),2)


if __name__=='__main__':unittest.main()
