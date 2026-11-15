"""Synthetic saved-file cases derived from real revision failures, not research data."""
from pathlib import Path
import sys, unittest, uuid, shutil, json
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from paths import ROOT,save,sha,read
from core import GateError
from delivery_review import audit_presentation,verify_delivery
from delivery_package import format_panel_notes,verify_package,write_notes
from project_intake import panel_candidates


class SlidesRegressions(unittest.TestCase):
    def setUp(self):
        self.base=ROOT/'临时文件'/('排图回归_'+uuid.uuid4().hex);self.base.mkdir(parents=True)
    def tearDown(self):
        shutil.rmtree(self.base)
    def deck(self):
        from pptx import Presentation
        from pptx.util import Pt
        prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
        return prs,slide,Pt
    def test_group_scaling_and_inheritance_do_not_pass_raw_working_size(self):
        prs,slide,Pt=self.deck();group=slide.shapes.add_group_shape()
        text=group.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(30));text.name='panel_a'
        p=text.text_frame.paragraphs[0];p.font.size=Pt(18);p.add_run().text='a'
        group.width=Pt(50);group.height=Pt(15)
        path=self.base/'缩放.pptx';prs.save(path)
        r=audit_presentation(path,dict(minimum_effective_font_pt=12,integer_working_sizes=True))
        metric=r['pages'][0][0]['fonts'][0]
        self.assertEqual(metric['working_pt'],18);self.assertEqual(metric['origin'],'paragraph')
        self.assertAlmostEqual(metric['geometric_estimate_pt'],9)
        self.assertIsNone(metric['effective_pt'])
        self.assertIn('font_size_requires_native_calibration',{f['kind'] for f in r['findings']})
        self.assertNotIn('small_effective_font',{f['kind'] for f in r['findings']})
        save(self.base/'目标.json',dict(schema_version='delivery-requirements-0.1',observations=[dict(id='font',object_id='panel_a',kind='effective_min_font_pt',expected=12)]))
        self.assertEqual(verify_delivery(self.base/'目标.json',path)['status'],'PENDING_NATIVE_CHECKS')
    def test_later_picture_covering_letter_is_candidate_with_position(self):
        from PIL import Image
        prs,slide,Pt=self.deck();t=slide.shapes.add_textbox(Pt(20),Pt(20),Pt(30),Pt(20));t.text='e';t.name='e'
        Image.new('RGB',(100,100),'blue').save(self.base/'图.png')
        pic=slide.shapes.add_picture(str(self.base/'图.png'),Pt(20),Pt(20),Pt(50),Pt(50));pic.name='microscopy'
        path=self.base/'挡字.pptx';prs.save(path)
        r=audit_presentation(path);f=next(x for x in r['findings'] if x['kind']=='text_covered_by_later_object_candidate')
        self.assertEqual(f['object_ids'],['e','microscopy']);self.assertEqual(f['slide_index'],1)
        self.assertEqual(r['visual'],'PENDING')
        r=audit_presentation(path,dict(intentional_overlaps=[dict(object_ids=['e','microscopy'],reason='Synthetic permitted overlap')]))
        self.assertNotIn('text_covered_by_later_object_candidate',{f['kind'] for f in r['findings']})
    def test_typography_profile_does_not_become_universal_rule(self):
        prs,slide,Pt=self.deck();t=slide.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(20));p=t.text_frame.paragraphs[0]
        r=p.add_run();r.text='x';r.font.size=Pt(9.5)
        path=self.base/'排字.pptx';prs.save(path)
        self.assertNotIn('noninteger_working_font',{f['kind'] for f in audit_presentation(path)['findings']})
        self.assertIn('noninteger_working_font',{f['kind'] for f in audit_presentation(path,dict(integer_working_sizes=True))['findings']})
    def project(self):
        from PIL import Image
        Image.new('RGB',(200,100),'white').save(self.base/'横.png');Image.new('RGB',(100,100),'gray').save(self.base/'方.png')
        m=dict(schema_version='project-intake-0.1',project_id='SYNTHETIC',sources=[dict(id='A',kind='data_plot',path='横.png',review_status='CONFIRMED'),dict(id='B',kind='scientific_image',path='方.png',review_status='CONFIRMED')],
            panels=[dict(id='spectrum',source_id='A'),dict(id='inset',source_id='B')],canvas_mm=[180,100],margin_mm=5,gap_mm=4,label_band_mm=3,
            layout_variants=[dict(id='weighted',columns=[3,1],rows=[1],placements=[dict(panel_id='spectrum',row=0,column=0),dict(panel_id='inset',row=0,column=1)])])
        path=self.base/'项目.json';save(path,m);return path,m
    def test_weighted_layout_gives_spectrum_space_without_stretch(self):
        path,m=self.project();r=panel_candidates(path,self.base/'布局');a,b=r['candidates'][0]['panels']
        aw=a['bbox_mm'][2]-a['bbox_mm'][0];ah=a['bbox_mm'][3]-a['bbox_mm'][1];bw=b['bbox_mm'][2]-b['bbox_mm'][0]
        self.assertGreater(aw,2*bw);self.assertAlmostEqual(aw/ah,2)
        self.assertEqual(r['source_pixels_modified'],False)
    def test_preserved_local_placement_stays_exact_and_overlap_rejected(self):
        path,m=self.project();p=m['layout_variants'][0]['placements'][0];p.clear();p.update(panel_id='spectrum',preserve_bbox_mm=[5,5,125,65],preservation_source='adopted-layout:spectrum')
        path.write_text(json.dumps(m),encoding='utf-8');r=panel_candidates(path,self.base/'保留')
        self.assertEqual(r['candidates'][0]['panels'][0]['bbox_mm'],[5,5,125,65])
        m['layout_variants'][0]['placements'][1]=dict(panel_id='inset',preserve_bbox_mm=[80,20,120,60],preservation_source='adopted-layout:inset')
        path.write_text(json.dumps(m),encoding='utf-8')
        with self.assertRaisesRegex(GateError,'OVERLAP'):panel_candidates(path,self.base/'不许遮挡')
    def notes_data(self):
        prs,slide,Pt=self.deck()
        for _ in range(6):prs.slides.add_slide(prs.slide_layouts[6])
        source_ppt=self.base/'汇总来源.pptx';prs.save(source_ppt)
        sources=[dict(id='summary',kind='summary_ppt',title='合成数据汇总',version='v1',page=7,page_description='表征：红外与衍射',source_pptx=dict(path=source_ppt.name,sha256=sha(source_ppt))),dict(id='raw',kind='raw_data',path='光谱/原始表.csv',locator='吸收列'),dict(id='thesis',kind='thesis',title='合成论文',locator='图 2',relationship='related_only')]
        panels=[dict(id='ftir',label='c',title='各材料红外光谱',meaning='比较材料的特征吸收',source_ids=['summary','raw','thesis'],processing='保留全部有效谱点重绘，调整字体和排布')]
        return sources,panels
    def test_notes_distinguish_summary_raw_derived_thesis_and_page_offset(self):
        sources,panels=self.notes_data();text=format_panel_notes(panels[0],{s['id']:s for s in sources},'n')
        self.assertIn('第 7+n 页',text);self.assertIn('原始数据：光谱/原始表.csv',text);self.assertIn('尚未确认是同一数据',text)
        sources[1]['path']='C:/private/source.csv'
        with self.assertRaisesRegex(GateError,'RELATIVE_READER_PATH'):format_panel_notes(panels[0],{s['id']:s for s in sources})
    def test_notes_new_copy_preserves_slide_media_and_original_and_manual_notes(self):
        prs,slide,Pt=self.deck();t=slide.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(30));t.text='Approved figure'
        second=prs.slides.add_slide(prs.slide_layouts[6]);second.notes_slide.notes_text_frame.text='Human note unchanged'
        path=self.base/'人工版.pptx';prs.save(path);before=sha(path);sources,panels=self.notes_data()
        request=dict(artifact=dict(path=path.name,sha256=before),sources=sources,panels=panels,page_offset='n',slides=[dict(slide_index=1,panel_ids=['ftir'],expected_notes='')])
        save(self.base/'备注请求.json',request);r=write_notes(self.base/'备注请求.json',self.base/'新版')
        self.assertEqual(sha(path),before);self.assertTrue(r['unchanged_slide_xml']);self.assertTrue(r['unchanged_media_and_embedded_projects'])
        from pptx import Presentation
        self.assertEqual(Presentation(r['output']['path']).slides[1].notes_slide.notes_text_frame.text,'Human note unchanged')
        request['slides']=[dict(slide_index=2,panel_ids=['ftir'])];(self.base/'备注请求.json').write_text(json.dumps(request),encoding='utf-8')
        with self.assertRaisesRegex(GateError,'MANUAL_NOTES_CONFLICT'):write_notes(self.base/'备注请求.json',self.base/'冲突')
    def test_notes_can_add_missing_note_master_without_touching_slide_content(self):
        prs,slide,Pt=self.deck();path=self.base/'无备注.pptx';prs.save(path)
        sources,panels=self.notes_data();save(self.base/'补备注.json',dict(artifact=dict(path=path.name,sha256=sha(path)),sources=sources,panels=panels,slides=[dict(slide_index=1,panel_ids=['ftir'],allow_new_notes=True)]))
        r=write_notes(self.base/'补备注.json',self.base/'补后');self.assertTrue(r['unchanged_slide_xml'])
        from pptx import Presentation
        p=Presentation(r['output']['path']);self.assertIn('本次处理',p.slides[0].notes_slide.notes_text_frame.text)
    def test_manual_cleared_note_rejects_old_expectation_and_allows_explicit_empty(self):
        prs,slide,Pt=self.deck();slide.notes_slide.notes_text_frame.text='';path=self.base/'人工清空.pptx';prs.save(path)
        sources,panels=self.notes_data();m=dict(artifact=dict(path=path.name,sha256=sha(path)),sources=sources,panels=panels,slides=[dict(slide_index=1,panel_ids=['ftir'],expected_notes='Old assistant note')])
        save(self.base/'请求.json',m)
        with self.assertRaisesRegex(GateError,'MANUAL_NOTES_CONFLICT'):write_notes(self.base/'请求.json',self.base/'不应写入')
        m['slides'][0]['expected_notes']='';(self.base/'请求.json').write_text(json.dumps(m),encoding='utf-8')
        self.assertEqual(write_notes(self.base/'请求.json',self.base/'批准空白补写')['status'],'NOTES_WRITTEN_TO_NEW_COPY')
    def test_raw_table_project_without_summary_does_not_invent_missing_summary(self):
        panel=dict(id='size',label='a',title='矿物粒径分布',meaning='比较粒径分布',source_ids=['raw','derived'],processing='根据粒径原表分箱统计')
        sources=dict(raw=dict(id='raw',kind='raw_data',path='粒径/原表.csv'),derived=dict(id='derived',kind='derived_data',path='粒径/分箱表.csv'))
        text=format_panel_notes(panel,sources);self.assertNotIn('汇总',text);self.assertIn('派生数据',text)
        panel['summary_context']='specified_summary_missing'
        with self.assertRaisesRegex(GateError,'ABSENCE_FROM_SUMMARY'):format_panel_notes(panel,sources)
    def test_ungrouped_rotation_and_whole_page_scale_are_separate_from_group_estimate(self):
        from pptx.oxml.xmlchemy import OxmlElement
        prs,slide,Pt=self.deck();plain=slide.shapes.add_textbox(Pt(10),Pt(40),Pt(240),Pt(50));plain.name='plain';plain.rotation=90
        p=plain.text_frame.paragraphs[0];r=p.add_run();r.text='Native size';r.font.size=Pt(18)
        auto=slide.shapes.add_textbox(Pt(80),Pt(40),Pt(200),Pt(40));auto.name='auto';r=auto.text_frame.paragraphs[0].add_run();r.text='Fit candidate';r.font.size=Pt(18)
        norm=OxmlElement('a:normAutofit');norm.set('fontScale','50000');auto.text_frame._txBody.bodyPr.append(norm)
        path=self.base/'字体情形.pptx';prs.save(path);profile=dict(target_width_mm=prs.slide_width/36000/2,minimum_effective_font_pt=12)
        r=audit_presentation(path,profile);by={o['object_id']:o for o in r['pages'][0]}
        self.assertEqual(by['plain']['fonts'][0]['effective_pt'],9)
        self.assertIsNone(by['auto']['fonts'][0]['effective_pt'])
        self.assertNotIn('auto',{f['object_ids'][0] for f in r['findings'] if f['kind']=='small_effective_font'})
    def test_old_project_correct_hash_stays_pending_and_wrong_receipt_is_rejected(self):
        from PIL import Image
        pack=self.base/'交付包';pack.mkdir();old=pack/'旧绘图工程.json';old.write_text('{"sample":"Granite"}')
        current=pack/'当前绘图工程.json';current.write_text('{"sample":"Shale"}');raw=pack/'原表.csv';raw.write_text('x,y\n1,2\n')
        Image.new('RGB',(20,20),'blue').save(pack/'当前图.png')
        files=[dict(id=k,path=p.name,sha256=sha(p)) for k,p in [('project',old),('figure',pack/'当前图.png'),('raw',raw)]]
        m=dict(schema_version='research-delivery-0.1',package_root=pack.name,files=files,panels=[dict(id='one',destination='main',files=dict(current_project=['project'],final_figure=['figure'],raw_data=['raw']))])
        save(self.base/'当前包.json',m);r=verify_package(self.base/'当前包.json');self.assertEqual(r['status'],'PACKAGE_BINDINGS_PENDING')
        self.assertIn('current_project_binding_not_verified',{p['kind'] for p in r['pending']})
        save(pack/'原生绑定记录.json',dict(schema_version='native-plot-binding-0.1',project=dict(sha256=sha(current)),exports=[dict(sha256=sha(pack/'当前图.png'),graph_id='Graph1')],arrays=[],native_readback=dict(status='NOT_PERFORMED')))
        files.append(dict(id='receipt',path='原生绑定记录.json',sha256=sha(pack/'原生绑定记录.json')))
        m['panels'][0]['project_bindings']=[dict(project_file_id='project',final_file_id='figure',evidence_file_id='receipt')]
        (self.base/'当前包.json').write_text(json.dumps(m),encoding='utf-8');r=verify_package(self.base/'当前包.json')
        self.assertIn('project_export_binding_conflict',{f['kind'] for f in r['findings']})
    def test_current_presentation_media_binding_checks_actual_picture(self):
        from PIL import Image
        from pptx_tags import attach_tags,shape_nv
        pack=self.base/'交付包';pack.mkdir();Image.new('RGB',(20,20),'blue').save(pack/'当前图.png');Image.new('RGB',(20,20),'red').save(pack/'旧图.png')
        prs,slide,Pt=self.deck();pic=slide.shapes.add_picture(str(pack/'旧图.png'),Pt(10),Pt(10),Pt(100),Pt(100))
        attach_tags(slide,slide._element.cSld,dict(STUDIO_SLIDE_ID='F1'));attach_tags(slide,shape_nv(pic),dict(STUDIO_ID='panel_a',ASSET_ID='one'))
        prs.save(pack/'当前PPT.pptx')
        m=dict(schema_version='research-delivery-0.1',package_root=pack.name,current_presentation_file_ids=['deck'],files=[dict(id=k,path=n,sha256=sha(pack/n)) for k,n in [('deck','当前PPT.pptx'),('figure','当前图.png')]],
            panels=[dict(id='one',destination='main',files=dict(final_figure=['figure']),presentation_occurrences=[dict(deck_file_id='deck',slide_id='F1',object_id='panel_a',final_file_id='figure')])])
        save(self.base/'当前图绑定.json',m);r=verify_package(self.base/'当前图绑定.json')
        self.assertIn('presentation_panel_media_conflict',{f['kind'] for f in r['findings']})
    def test_notes_and_package_share_source_file_page_identity_across_versions(self):
        from pptx import Presentation
        prs,slide,Pt=self.deck();prs.save(self.base/'当前稿.pptx')
        def summary(name,count,target):
            deck=Presentation()
            for n in range(count):
                s=deck.slides.add_slide(deck.slide_layouts[6]);t=s.shapes.add_textbox(Pt(10),Pt(10),Pt(200),Pt(30));t.name='source_plot';t.text='same experiment' if n+1==target else 'unrelated '+str(n)
            p=self.base/name;deck.save(p);return p
        v1=summary('汇总v1.pptx',7,7);v2=summary('汇总v2.pptx',4,4)
        def catalog(path,page,version):return dict(schema_version='delivery-source-catalog-0.1',sources=[dict(id='summary',kind='summary_ppt',title='合成汇总',version=version,page=page,page_description='矿物吸收谱',object_ids=['source_plot'],source_pptx=dict(path=path.name,sha256=sha(path)))])
        save(self.base/'旧来源.json',catalog(v1,7,'v1'));save(self.base/'新来源.json',catalog(v2,4,'v2'))
        panel=dict(id='one',label='a',title='矿物吸收谱',meaning='比较吸收',source_ids=['summary'],processing='按确认谱线重画')
        request=dict(artifact=dict(path='当前稿.pptx',sha256=sha(self.base/'当前稿.pptx')),source_catalog=dict(path='旧来源.json',sha256=sha(self.base/'旧来源.json')),panels=[panel],slides=[dict(slide_index=1,panel_ids=['one'],expected_notes='')])
        save(self.base/'写备注.json',request);r=write_notes(self.base/'写备注.json',self.base/'已写');self.assertIn('第 7 页',r['slides'][0]['text'])
        pack=self.base/'交付包';pack.mkdir();shutil.copy2(r['output']['path'],pack/'当前PPT.pptx');shutil.copy2(self.base/'已写/来源备注记录.json',pack/'备注记录.json');shutil.copy2(v2,pack/'来源副本.pptx')
        m=dict(schema_version='research-delivery-0.1',package_root=pack.name,source_catalog=dict(path='新来源.json',sha256=sha(self.base/'新来源.json')),
            files=[dict(id=k,path=n,sha256=sha(pack/n)) for k,n in [('deck','当前PPT.pptx'),('notes','备注记录.json'),('page','来源副本.pptx')]],
            panels=[dict(id='one',destination='main',files=dict(source_page=['page']),source_pages=[dict(file_id='page',source_id='summary',page_in_copy=4)])],notes_records=[dict(file_id='notes',deck_file_id='deck')])
        save(self.base/'跨版本包.json',m);r=verify_package(self.base/'跨版本包.json')
        self.assertIn('notes_source_identity_conflict',{f['kind'] for f in r['findings']})
    def test_required_notes_cover_actual_pages_and_each_panel_not_just_source_records(self):
        prs,slide,Pt=self.deck();prs.slides.add_slide(prs.slide_layouts[6]);parent=self.base/'父本.pptx';prs.save(parent)
        panels=[dict(id=identity,label=label,title='合成数据 '+label,meaning='用于验证逐小图备注覆盖',source_ids=['raw'],processing='从合成原表绘图') for identity,label in [('one','a'),('two','b')]]
        request=dict(artifact=dict(path=parent.name,sha256=sha(parent)),sources=[dict(id='raw',kind='raw_data',path='合成原表.csv')],panels=panels,
            slides=[dict(slide_index=1,panel_ids=['one'],expected_notes=''),dict(slide_index=2,panel_ids=['two'],expected_notes='')])
        save(self.base/'备注.json',request);r=write_notes(self.base/'备注.json',self.base/'备注结果');pack=self.base/'交付';pack.mkdir()
        shutil.copy2(r['output']['path'],pack/'当前.pptx');shutil.copy2(self.base/'备注结果/来源备注记录.json',pack/'记录.json')
        m=dict(schema_version='research-delivery-0.1',package_root=pack.name,requires_notes_binding=True,
            files=[dict(id=k,path=n,sha256=sha(pack/n)) for k,n in [('deck','当前.pptx'),('record','记录.json')]],
            panels=[dict(id=k,destination='main',files={}) for k in ('one','two')],notes_records=[dict(file_id='record',deck_file_id='deck')],
            notes_requirements=[dict(deck_file_id='deck',slides=[dict(slide_index=1,panel_ids=['one']),dict(slide_index=2,panel_ids=['two'])])])
        save(self.base/'包.json',m);self.assertEqual(verify_package(self.base/'包.json')['status'],'PACKAGE_RECORDS_MATCH')
        good=read(pack/'记录.json')
        for kind in ('empty','missing','wrong_page'):
            bad=json.loads(json.dumps(good))
            if kind=='empty':bad['slides']=[]
            elif kind=='missing':bad['slides']=bad['slides'][:1]
            else:
                bad['slides'][0]['slide_index']=2;bad['slides'][1]['slide_index']=1
            (pack/'记录.json').write_text(json.dumps(bad),encoding='utf-8');m['files'][1]['sha256']=sha(pack/'记录.json');(self.base/'包.json').write_text(json.dumps(m),encoding='utf-8')
            result=verify_package(self.base/'包.json');self.assertEqual(result['status'],'PACKAGE_REQUIRES_REPAIR',kind)
            self.assertIn('notes_required_panels_missing',{f['kind'] for f in result['findings']},kind)
        (pack/'记录.json').write_text(json.dumps(good),encoding='utf-8');m['files'][1]['sha256']=sha(pack/'记录.json')
        m.pop('notes_requirements');(self.base/'包.json').write_text(json.dumps(m),encoding='utf-8');result=verify_package(self.base/'包.json')
        self.assertEqual(result['status'],'PACKAGE_BINDINGS_PENDING');self.assertIn('notes_coverage_scope_missing',{p['kind'] for p in result['pending']})
    def test_two_deck_versions_can_have_different_explicit_note_scopes(self):
        pack=self.base/'交付';pack.mkdir();files=[];links=[];requirements=[]
        for i,identity in enumerate(('one','two'),1):
            prs,slide,Pt=self.deck();parent=self.base/f'父本{i}.pptx';prs.save(parent)
            panel=dict(id=identity,label='a',title='该版选定数据',meaning='合成覆盖测试',source_ids=['raw'],processing='沿用该版数据')
            request=dict(artifact=dict(path=parent.name,sha256=sha(parent)),sources=[dict(id='raw',kind='raw_data',path='原表.csv')],panels=[panel],slides=[dict(slide_index=1,panel_ids=[identity],expected_notes='')])
            save(self.base/f'请求{i}.json',request);r=write_notes(self.base/f'请求{i}.json',self.base/f'输出{i}')
            shutil.copy2(r['output']['path'],pack/f'版{i}.pptx');shutil.copy2(self.base/f'输出{i}/来源备注记录.json',pack/f'记录{i}.json')
            files.extend([dict(id=f'deck{i}',path=f'版{i}.pptx',sha256=sha(pack/f'版{i}.pptx')),dict(id=f'record{i}',path=f'记录{i}.json',sha256=sha(pack/f'记录{i}.json'))])
            links.append(dict(file_id=f'record{i}',deck_file_id=f'deck{i}'));requirements.append(dict(deck_file_id=f'deck{i}',slides=[dict(slide_index=1,panel_ids=[identity])]))
        m=dict(schema_version='research-delivery-0.1',package_root=pack.name,requires_notes_binding=True,files=files,notes_records=links,notes_requirements=requirements,panels=[dict(id=k,destination='main',files={}) for k in ('one','two')])
        save(self.base/'双版本.json',m);self.assertEqual(verify_package(self.base/'双版本.json')['status'],'PACKAGE_RECORDS_MATCH')
    def test_valid_package_keeps_actual_original_name_and_time_and_checks_source_slide(self):
        prs,slide,Pt=self.deck();origin=self.base/'来源';origin.mkdir();source_page=origin/'数据汇总_第7页.pptx';prs.save(source_page)
        raw=origin/'原始表.csv';raw.write_text('x,y\n1,2\n')
        pack=self.base/'交付包';pack.mkdir();shutil.copy2(raw,pack/raw.name);shutil.copy2(source_page,pack/source_page.name)
        files=[dict(id='raw',path=raw.name,sha256=sha(raw),original_source=dict(path='来源/'+raw.name,sha256=sha(raw))),dict(id='page',path=source_page.name,sha256=sha(source_page))]
        m=dict(schema_version='research-delivery-0.1',package_root='交付包',expected_panel_ids=['one'],required_roles=['raw_data','source_page'],files=files,
            panels=[dict(id='one',figure_id='F1',destination='reserve',files=dict(raw_data=['raw'],source_page=['page']),source_pages=[dict(file_id='page',source_version='v1',original_page=1,source_pptx=dict(path='来源/'+source_page.name,sha256=sha(source_page)))])],figures=[dict(id='F1',panel_ids=['one'])])
        save(self.base/'完整包.json',m);self.assertEqual(verify_package(self.base/'完整包.json')['status'],'PACKAGE_RECORDS_MATCH')
        m['panels'][0]['source_pages'][0]['page_in_copy']=2;(self.base/'完整包.json').write_text(json.dumps(m),encoding='utf-8')
        self.assertIn('source_page_index_invalid',{f['kind'] for f in verify_package(self.base/'完整包.json')['findings']})
    def test_openable_wrong_source_page_is_detected_from_actual_content(self):
        prs,slide,Pt=self.deck();slide.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(30)).text='Experiment A'
        second=prs.slides.add_slide(prs.slide_layouts[6]);second.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(30)).text='Experiment B'
        source_page=self.base/'原汇总.pptx';prs.save(source_page)
        pack=self.base/'交付包';pack.mkdir();shutil.copy2(source_page,pack/'错误来源页.pptx')
        m=dict(schema_version='research-delivery-0.1',package_root='交付包',files=[dict(id='page',path='错误来源页.pptx',sha256=sha(source_page))],
            panels=[dict(id='one',figure_id='F1',destination='main',files=dict(source_page=['page']),source_pages=[dict(file_id='page',source_version='v1',original_page=1,page_in_copy=2,source_pptx=dict(path=source_page.name,sha256=sha(source_page)))])])
        save(self.base/'错页.json',m);r=verify_package(self.base/'错页.json')
        self.assertIn('source_page_content_mismatch',{f['kind'] for f in r['findings']});self.assertFalse(r['source_page_checks'][0]['object_payloads_match'])
    def test_package_detects_missing_stale_and_unaccounted_panels(self):
        pack=self.base/'交付包';pack.mkdir();(pack/'当前.csv').write_text('x,y\n1,2\n')
        m=dict(schema_version='research-delivery-0.1',package_root='交付包',expected_panel_ids=['one','two'],required_roles=['raw_data','current_project','final_figure'],
            files=[dict(id='data',path='当前.csv',sha256='0'*64)],panels=[dict(id='one',figure_id='F1',destination='main',files=dict(raw_data=['data']))])
        save(self.base/'包.json',m);r=verify_package(self.base/'包.json');kinds={f['kind'] for f in r['findings']}
        self.assertTrue({'changed_file','missing_role','panel_lost'}<=kinds)
        self.assertEqual((pack/'当前.csv').read_text(),'x,y\n1,2\n')
    def test_package_rejects_external_dependency_and_unapproved_omission(self):
        pack=self.base/'交付包';pack.mkdir();m=dict(schema_version='research-delivery-0.1',package_root='交付包',files=[],panels=[dict(id='one',destination='excluded')]);save(self.base/'包.json',m)
        self.assertIn('exclusion_unexplained',{f['kind'] for f in verify_package(self.base/'包.json')['findings']})
        m['files']=[dict(id='bad',path='../原始数据.csv')];(self.base/'包.json').write_text(json.dumps(m),encoding='utf-8')
        with self.assertRaisesRegex(GateError,'OUTSIDE_ROOT'):verify_package(self.base/'包.json')


if __name__=='__main__':unittest.main()
