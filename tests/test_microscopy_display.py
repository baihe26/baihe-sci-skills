from pathlib import Path
import sys, tempfile, unittest, copy
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from paths import ROOT,sha
from microscopy_sources import inspect_microscopy,compare_displays,scale_bar_check


class MicroscopyDisplayTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='显微继承_',dir=ROOT/'临时文件');self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)

    def test_actual_ppt_preserves_image_effects_crop_flip_and_group(self):
        from PIL import Image
        from pptx import Presentation
        from pptx.util import Inches
        from pptx.oxml.xmlchemy import OxmlElement
        image=self.root/'texture.png';Image.new('RGB',(200,100),(60,70,80)).save(image)
        prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
        group=slide.shapes.add_group_shape();pic=group.shapes.add_picture(str(image), Inches(1), Inches(1), width=Inches(4))
        pic.crop_left=.1;pic.rotation=10
        pic._element.spPr.xfrm.set('flipH','1')
        lum=OxmlElement('a:lum');lum.set('bright','20000');lum.set('contrast','10000')
        pic._element.blipFill.blip.append(lum)
        path=self.root/'selected.pptx';prs.save(path);before=sha(path)
        report=inspect_microscopy(path,[1]);r=report['images'][0]
        self.assertEqual(r['media_sha256'],sha(image))
        self.assertEqual(r['display']['image_effects'][0]['attributes']['bright'],'20000')
        self.assertEqual(r['display']['crop']['attributes']['l'],'10000')
        self.assertEqual(r['display']['transform']['attributes']['flipH'],'1')
        self.assertEqual(len(r['display']['group_transforms']),1)
        stripped=copy.deepcopy(r);stripped['display']['image_effects']=[]
        self.assertEqual(compare_displays(r,stripped)['status'],'FAIL')
        self.assertEqual(sha(path),before)

    def test_scaling_same_field_does_not_make_bar_wrong(self):
        cal=dict(instrument_bar_px=100,instrument_bar_value=1,unit='um')
        small=scale_bar_check(cal,1000,50,5,1)
        large=scale_bar_check(cal,1000,100,10,1)
        self.assertEqual(small['status'],'PASS');self.assertEqual(large['status'],'PASS')
        wrong=scale_bar_check(cal,1000,100,10,.3)
        self.assertEqual(wrong['status'],'CHECK_CALIBRATION')

    def test_crop_calibration_is_not_full_field_width(self):
        cal=dict(instrument_bar_px=100,instrument_bar_value=1,unit='um')
        self.assertEqual(scale_bar_check(cal,500,50,10,1)['status'],'PASS')
        self.assertEqual(scale_bar_check(cal,1000,50,10,1)['status'],'CHECK_CALIBRATION')

    def test_translation_permission_never_authorizes_mirror_or_stretch(self):
        node=lambda tag,attrs:dict(tag=tag,attributes=attrs,children=[])
        xfrm=dict(attributes={},children=[node('off',dict(x='10',y='20')),node('ext',dict(cx='200',cy='100'))])
        a=dict(media_sha256='same',display=dict(transform=xfrm))
        b=copy.deepcopy(a);b['display']['transform']['children'][0]['attributes']['x']='30'
        self.assertEqual(compare_displays(a,b,['translate'])['status'],'PASS')
        b['display']['transform']['attributes']['flipH']='1'
        self.assertEqual(compare_displays(a,b,['translate'])['status'],'FAIL')
        b=copy.deepcopy(a);b['display']['transform']['children'][1]['attributes']=dict(cx='400',cy='200')
        self.assertEqual(compare_displays(a,b,['uniform_scale'])['status'],'PASS')
        b['display']['transform']['children'][1]['attributes']['cy']='100'
        self.assertEqual(compare_displays(a,b,['uniform_scale'])['status'],'FAIL')
        from core import GateError
        with self.assertRaisesRegex(GateError,'TOO_BROAD'):compare_displays(a,b,['transform'])

if __name__=='__main__':unittest.main()
