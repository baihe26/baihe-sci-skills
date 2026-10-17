"""Small checks for the transfer boundary, without native apps or copying runtimes."""
from pathlib import Path
import unittest,sys,uuid,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'工作台/源码'))
from migration_pack import function_subset
from migration_setup import verify


class MigrationTests(unittest.TestCase):
    def folder(self):
        p=ROOT/'工作台/临时文件'/('迁移检查_'+uuid.uuid4().hex);p.mkdir(parents=True);return p

    def test_extract_only_required_helpers(self):
        p=self.folder()/'source.py';p.write_text("SECRET_DATA=['do not transfer']\ndef read(p):\n return p\ndef unused():\n return SECRET_DATA\n",encoding='utf-8')
        text=function_subset(p,['read'],'from pathlib import Path')
        self.assertNotIn('SECRET_DATA',text);self.assertNotIn('unused',text)
        context={};exec(text,context);self.assertEqual(context['read']('x'),'x')
        with self.assertRaises(RuntimeError):function_subset(p,['missing'],'')

    def test_manifest_binds_files_and_refuses_parent_traversal(self):
        root=self.folder();file=root/'module.py';file.write_text('original',encoding='utf-8')
        row=dict(path='module.py',sha256=hashlib.sha256(file.read_bytes()).hexdigest())
        manifest=root/'配套文件清单.json';manifest.write_text(json.dumps(dict(files=[row])),encoding='utf-8')
        self.assertEqual(verify(root),1)
        file.write_text('changed',encoding='utf-8')
        with self.assertRaises(RuntimeError):verify(root)
        row['path']='../module.py';manifest.write_text(json.dumps(dict(files=[row])),encoding='utf-8')
        with self.assertRaises(ValueError):verify(root)


if __name__=='__main__':unittest.main()
