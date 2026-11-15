"""Small real-world PPT edits must preserve runs, notes and unrelated package parts."""
from pathlib import Path
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from paths import ROOT,sha
from core import GateError
from ppt_local_patch import edit_ppt,inspect_ppt
from pptx_tags import read_package,xml,NS


class LocalPptPatchTests(unittest.TestCase):
    def setUp(self):
        from pptx import Presentation
        from pptx.util import Pt
        from pptx.dml.color import RGBColor
        self.tmp=tempfile.TemporaryDirectory(prefix='PPT局部修订_',dir=ROOT/'临时文件');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'人工父本.pptx'
        prs=Presentation()
        first=prs.slides.add_slide(prs.slide_layouts[6]);title=first.shapes.add_textbox(Pt(20),Pt(20),Pt(300),Pt(40))
        title.name='title';run=title.text_frame.paragraphs[0].add_run();run.text='Original title';run.font.name='Arial';run.font.size=Pt(20);run.font.bold=True;run.font.color.rgb=RGBColor(1,2,3)
        first.notes_slide.notes_text_frame.text='人工备注，必须逐字保留。'
        second=prs.slides.add_slide(prs.slide_layouts[6]);label=second.shapes.add_textbox(Pt(80),Pt(190),Pt(30),Pt(25));label.name='covered_e'
        label.text='e';label.text_frame.paragraphs[0].runs[0].font.size=Pt(22)
        mixed=second.shapes.add_textbox(Pt(200),Pt(20),Pt(80),Pt(30));mixed.name='chemical'
        p=mixed.text_frame.paragraphs[0];a=p.add_run();a.text='H';a.font.size=Pt(18)
        b=p.add_run();b.text='2';b.font.size=Pt(12);b._r.get_or_add_rPr().set('baseline','-25000')
        c=p.add_run();c.text='O';c.font.size=Pt(18)
        third=prs.slides.add_slide(prs.slide_layouts[6]);third.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(20)).text='Unchanged slide'
        prs.save(self.source)
        self.index=inspect_ppt(self.source);self.title=next(r for r in self.index['slides'][0]['objects'] if r['name']=='title')
        self.label=next(r for r in self.index['slides'][1]['objects'] if r['name']=='covered_e')
        self.mixed=next(r for r in self.index['slides'][1]['objects'] if r['name']=='chemical')

    def request(self,changes,name='请求.json'):
        request=dict(schema_version='ppt-local-patch-0.1',source=dict(path=self.source.name,sha256=sha(self.source)),changes=changes)
        path=self.root/name;path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8');return path

    def test_title_and_letter_patch_preserves_other_parts_and_run_properties(self):
        from pptx import Presentation
        original=read_package(self.source);before=sha(self.source)
        req=self.request([dict(slide_number=1,shape_id=self.title['shape_id'],expected_object_sha256=self.title['object_sha256'],fields=dict(text='Hydrogel characterization',font_name='Calibri',font_pt=22)),
                          dict(slide_number=2,shape_id=self.label['shape_id'],fields=dict(position_pt=[46,161]))])
        result=edit_ppt(req,self.root/'输出');final=read_package(result['file']['path'])
        self.assertEqual(sha(self.source),before)
        for part,blob in original.items():
            if part not in result['changed_parts']:self.assertEqual(blob,final[part],part)
        prs=Presentation(result['file']['path']);title=prs.slides[0].shapes[0]
        self.assertEqual(title.text,'Hydrogel characterization');run=title.text_frame.paragraphs[0].runs[0]
        self.assertEqual(run.font.name,'Calibri');self.assertEqual(run.font.size.pt,22);self.assertTrue(run.font.bold)
        self.assertEqual(str(run.font.color.rgb),'010203')
        label=prs.slides[1].shapes[0];self.assertAlmostEqual(label.left/12700,46);self.assertAlmostEqual(label.top/12700,161)
        self.assertEqual(result['native_reopen'],'PENDING')

    def test_complex_text_requires_explicit_runs_and_keeps_subscript(self):
        req=self.request([dict(slide_number=2,shape_id=self.mixed['shape_id'],fields=dict(text='H2O changed'))])
        with self.assertRaisesRegex(GateError,'COMPLEX_TEXT_USE_EXPLICIT_RUNS'):edit_ppt(req,self.root/'blocked')
        req=self.request([dict(slide_number=2,shape_id=self.mixed['shape_id'],fields=dict(runs=[dict(paragraph_index=1,run_index=3,expected_text='O',text='S')]))],'逐run.json')
        result=edit_ppt(req,self.root/'逐run输出');root=xml(read_package(result['file']['path'])['ppt/slides/slide2.xml'])
        runs=root.xpath('.//p:sp[p:nvSpPr/p:cNvPr[@name="chemical"]]/p:txBody/a:p/a:r',namespaces=NS)
        self.assertEqual(''.join(r.findtext('a:t','',NS) for r in runs),'H2S');self.assertEqual(runs[1].find('a:rPr',NS).get('baseline'),'-25000')
        self.assertEqual(runs[1].find('a:rPr',NS).get('sz'),'1200')

    def test_changed_source_and_changed_object_fail_before_output(self):
        req=self.request([dict(slide_number=1,shape_id=self.title['shape_id'],expected_object_sha256='0'*64,fields=dict(font_pt=22))])
        with self.assertRaisesRegex(GateError,'OBJECT_CHANGED'):edit_ppt(req,self.root/'stale-object')
        request=json.loads(req.read_text(encoding='utf-8'));request['source']['sha256']='0'*64;req.write_text(json.dumps(request),encoding='utf-8')
        with self.assertRaisesRegex(GateError,'SOURCE_HASH_CONFLICT'):edit_ppt(req,self.root/'stale-parent')
        self.assertFalse((self.root/'stale-object').exists());self.assertFalse((self.root/'stale-parent').exists())

    def test_task_context_rejects_old_assistant_parent(self):
        adopted=self.root/'新人工父本.pptx';shutil.copy2(self.source,adopted)
        context=dict(schema_version='task-context-0.1',project_id='Synthetic',stage='revise',modules=['local'],parent=dict(path=adopted.name,sha256=sha(adopted)))
        cp=self.root/'上下文.json';cp.write_text(json.dumps(context),encoding='utf-8')
        req=self.request([dict(slide_number=1,shape_id=self.title['shape_id'],fields=dict(font_pt=22))])
        with patch.dict(os.environ,BAIHE_SCI_TASK_CONTEXT=str(cp)):
            with self.assertRaisesRegex(ValueError,'NOT_ADOPTED_PARENT'):edit_ppt(req,self.root/'old')

    def test_grouped_movement_uses_slide_coordinates_and_keeps_notes(self):
        from pptx import Presentation
        from pptx.util import Pt
        prs=Presentation(self.source);slide=prs.slides[2]
        first=slide.shapes[0];group=slide.shapes.add_group_shape([first]);group.left=Pt(100);group.top=Pt(100);group.width=Pt(200);group.height=Pt(40)
        prs.save(self.source);index=inspect_ppt(self.source);target=next(r for r in index['slides'][2]['objects'] if r['shape_id']==first.shape_id)
        req=self.request([dict(slide_number=3,shape_id=target['shape_id'],fields=dict(move_pt=[10,5]))])
        result=edit_ppt(req,self.root/'group');observed=next(r for r in inspect_ppt(result['file']['path'])['slides'][2]['objects'] if r['shape_id']==target['shape_id'])
        self.assertAlmostEqual(observed['position_pt'][0],target['position_pt'][0]+10);self.assertAlmostEqual(observed['position_pt'][1],target['position_pt'][1]+5)
        before=read_package(self.source);after=read_package(result['file']['path'])
        for p in before:
            if p.startswith('ppt/notesSlides/'):self.assertEqual(before[p],after[p])

    def test_generic_font_changes_chinese_east_asian_domain(self):
        from pptx import Presentation
        from pptx.oxml.xmlchemy import OxmlElement
        prs=Presentation(self.source);run=prs.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
        run.text='中文字体核对'
        ea=OxmlElement('a:ea');ea.set('typeface','微软雅黑');run._r.get_or_add_rPr().append(ea)
        cs=OxmlElement('a:cs');cs.set('typeface','Arial');run._r.get_or_add_rPr().append(cs)
        prs.save(self.source)
        req=self.request([dict(slide_number=1,shape_id=self.title['shape_id'],fields=dict(font_name='等线'))])
        result=edit_ppt(req,self.root/'中文输出');item=inspect_ppt(result['file']['path'])['slides'][0]['objects'][0]
        self.assertEqual(item['runs'][0]['fonts'],dict(latin='等线',east_asian='等线',complex_script='等线'))
        self.assertEqual(item['text'],'中文字体核对')
        run=Presentation(result['file']['path']).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
        self.assertTrue(run.font.bold);self.assertEqual(str(run.font.color.rgb),'010203')

    def test_script_font_is_scoped_and_mixed_runs_are_preserved(self):
        from pptx import Presentation
        from pptx.oxml.xmlchemy import OxmlElement
        prs=Presentation(self.source);shape=prs.slides[1].shapes[1]
        for run in shape.text_frame.paragraphs[0].runs:
            run.font.name='Calibri';ea=OxmlElement('a:ea');ea.set('typeface','微软雅黑');run._r.get_or_add_rPr().append(ea)
        prs.save(self.source)
        req=self.request([dict(slide_number=2,shape_id=self.mixed['shape_id'],fields=dict(runs=[dict(paragraph_index=1,run_index=2,font_east_asian='等线')]))])
        result=edit_ppt(req,self.root/'限定中文域');item=next(r for r in inspect_ppt(result['file']['path'])['slides'][1]['objects'] if r['shape_id']==self.mixed['shape_id'])
        self.assertEqual([r['fonts']['east_asian'] for r in item['runs']],['微软雅黑','等线','微软雅黑'])
        self.assertEqual([r['fonts']['latin'] for r in item['runs']],['Calibri']*3)
        saved=Presentation(result['file']['path']);middle=saved.slides[1].shapes[1].text_frame.paragraphs[0].runs[1]
        self.assertEqual(middle._r.get_or_add_rPr().get('baseline'),'-25000');self.assertEqual(middle.font.size.pt,12)
        req=self.request([dict(slide_number=1,shape_id=self.title['shape_id'],fields=dict(font_name='Calibri',font_east_asian='等线'))],'冲突字体.json')
        with self.assertRaisesRegex(GateError,'AMBIGUOUS_GENERIC_AND_SCRIPT_FONT'):edit_ppt(req,self.root/'conflict')


if __name__=='__main__':unittest.main()
