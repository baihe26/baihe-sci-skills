import importlib.util,json,tempfile,unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'工作台/源码/public_setup.py'
spec=importlib.util.spec_from_file_location('public_setup_for_test',SOURCE)
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


class PublicSetupTest(unittest.TestCase):
    def test_configuration_survives_move_and_preserves_custom_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'原目录';root.mkdir()
            existing=root/'baihe-sci.local.json';existing.write_text('{"private":"keep"}',encoding='utf-8')
            path=setup.write_configuration(root);before=path.read_bytes()
            moved=Path(folder)/'移动后';root.rename(moved)
            again=setup.write_configuration(moved)
            self.assertEqual(before,again.read_bytes())
            self.assertEqual((moved/'baihe-sci.local.json').read_text(encoding='utf-8'),'{"private":"keep"}')
            self.assertTrue(all(not Path(v).is_absolute() for v in json.loads(before).values() if isinstance(v,str)))
            again.write_text('{"manual":"preserve"}',encoding='utf-8')
            with self.assertRaises(RuntimeError):setup.write_configuration(moved)
            self.assertEqual(json.loads(again.read_text(encoding='utf-8')),{'manual':'preserve'})


if __name__=='__main__': unittest.main()
