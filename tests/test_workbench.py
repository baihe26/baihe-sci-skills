"""Portable contract checks; no COM calls, research data, or external engines."""
from pathlib import Path
import sys,unittest,os,json,uuid,subprocess,copy
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from paths import ROOT,save,sha,read
from core import GateError,route,writable,source,new_task,readable,impact,require_display_equivalent
from recovery_journal import Journal,inspect_recovery

class WorkbenchTests(unittest.TestCase):
    def temporary(self,suffix=''):
        p=ROOT/'临时文件'/('测试_'+uuid.uuid4().hex+suffix);p.parent.mkdir(parents=True,exist_ok=True);return p
    def test_independent_routes(self):
        for text,module in [('只把这个表画成图','plot'),('帮我设计，先不画最终版','designer'),('这张PNG别重新设计，做成可编辑','vector'),('按已批准SceneGraph画出来','vector'),('这些图已经确认，排成汇报','ppt'),('只改这一页','local'),('更新引用，总稿和小稿','update')]:self.assertEqual(route(text),[module])
    def test_ambiguous_intent(self):
        with self.assertRaises(GateError):route('看看')
    def test_outside_output(self):
        with self.assertRaises(GateError):writable(ROOT.parent/'不允许输出')
    def test_source_hash_mismatch(self):
        p=self.temporary('.txt');p.write_text('synthetic',encoding='utf-8')
        with self.assertRaises(GateError):source(p,'0'*64)
        self.assertEqual(source(p)['sha256'],sha(p))
    def test_duplicate_request(self):
        key='测试_'+uuid.uuid4().hex;new_task('只作图','SYNTHETIC_TEST',request_id=key)
        with self.assertRaises(GateError):new_task('只作图','SYNTHETIC_TEST',request_id=key)
    def test_final_size(self):
        self.assertEqual(readable(7,89,250)['status'],'SPLIT_OR_DISPLAY_VARIANT_REQUIRED')
        self.assertEqual(readable(7,89,600)['status'],'PASS')
    def test_manual_conflict(self):
        refs=[dict(reference_id='a',asset_id='A',object_digest='first'),dict(reference_id='b',asset_id='B',object_digest='second')]
        self.assertEqual([r['update_status'] for r in impact(refs,'A','r2',dict(a='moved'))],['CONFLICT'])
    def test_unknown_and_truncated_recovery(self):
        p=self.temporary('.jsonl');j=Journal(p,'manifest');token=j.begin('slide',dict(id='shape'))
        self.assertEqual(inspect_recovery(p,'manifest')['status'],'OUTCOME_UNKNOWN')
        self.assertFalse(inspect_recovery(p,'manifest')['automatic_retry_allowed'])
        j.commit(token,1);self.assertEqual(inspect_recovery(p,'manifest')['status'],'RECORDED')
        with self.assertRaises(ValueError):inspect_recovery(p,'changed')
        with p.open('a',encoding='utf-8') as f:f.write('{truncated')
        self.assertTrue(inspect_recovery(p,'manifest')['truncated_log'])
    def test_display_semantics(self):
        c=dict(statistical_n={'A':3},uncertainty={'kind':'SD'},denominator={'kind':'per_well'},source={'sha256':'synthetic'},plot_bindings={'x':'real_x'},y_variable={'unit':'a.u.'})
        s=dict(groups={'A':{'label':'Control'}},x_title='Time',y_title='Signal',x_scale='linear',y_scale='linear')
        self.assertTrue(require_display_equivalent(c,s,copy.deepcopy(c),copy.deepcopy(s)))
        for key,value in [('statistical_n',{'A':4}),('uncertainty',{'kind':'SEM'}),('denominator',{'kind':'per_cell'}),('source',{'sha256':'changed'}),('plot_bindings',{'x':'category'}),('y_variable',{'unit':'%'} )]:
            changed=copy.deepcopy(c);changed[key]=value
            with self.subTest(key=key),self.assertRaises(GateError):require_display_equivalent(c,s,changed,s)
        changed=copy.deepcopy(s);changed['y_title']='Changed'
        with self.assertRaises(GateError):require_display_equivalent(c,s,c,changed)
    def test_configless_doctor_and_safe_stop(self):
        env=dict(os.environ,BAIHE_SCI_CONFIG=str(self.temporary('.json')),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        cli=REPO/'工作台/源码/workbench.py'
        r=subprocess.run([sys.executable,str(cli),'--doctor'],capture_output=True,text=True,encoding='utf-8',env=env)
        self.assertEqual(r.returncode,0,r.stderr);report=json.loads(r.stdout)
        self.assertFalse(report['config_present']);self.assertEqual(len(report['routes']),5);self.assertTrue(all(x['missing'] for x in report['routes']))
        dest=self.temporary();r=subprocess.run([sys.executable,str(cli),'--module','vector','--scene',str(REPO/'示例/简单科学关系/IllustratorSceneGraph.json'),'--out',str(dest)],capture_output=True,text=True,encoding='utf-8',env=env)
        self.assertEqual(r.returncode,2,r.stderr);self.assertIn('DEPENDENCY_NOT_CONFIGURED',r.stdout);self.assertFalse(dest.exists())
    def test_relative_source_fixture(self):
        p=REPO/'示例/简单科学关系';spec=read(p/'FigureSpec.json');binding=read(p/'scientific_binding.json')
        self.assertEqual(sha(p/'合成来源.txt'),spec['metadata']['input_sha256'])
        self.assertEqual(sha(p/binding['source_file']['path']),binding['source_file']['sha256'])
        for c in spec['scientific_claims']:
            span=c['source_span'];self.assertEqual(spec['metadata']['input_text'][span['start']:span['end']],span['quote'])

if __name__=='__main__':unittest.main()
