"""Author-parent, content conservation, scoped decisions and actual repair receipts."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'工作台/源码'))
from paths import ROOT,sha
from core import writable,route,GateError,require_display_equivalent
from task_context import load_context,check_stage,resolve_preferences,require_parent_match
from revision_checks import compare_content,review_closure


class RevisionContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='修订接入_',dir=ROOT/'临时文件')
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def test_manual_parent_is_current_not_latest_assistant_file(self):
        parent=self.base/'人工另存.txt';parent.write_text('author removed explanation')
        context=self.base/'task.json'
        context.write_text(json.dumps(dict(schema_version='task-context-0.1',project_id='synthetic',stage='revise',
            parent=dict(path=parent.name,sha256=sha(parent)),authorized_output_roots=['next'],protected_paths=[])))
        record=load_context(context)
        self.assertEqual(record['parent']['path'],str(parent))
        with self.assertRaisesRegex(GateError,'PROTECTED'):
            writable(parent,record)
        parent.write_text('new manual save')
        with self.assertRaisesRegex(ValueError,'MANUAL_PARENT_CHANGED'):
            load_context(context)

    def test_explicit_module_accepts_natural_revision_not_keyword_guess(self):
        self.assertEqual(route('沿人工版修改并同步相关资料',explicit='ppt'),['ppt'])
        self.assertEqual(route('看看这个工作怎么设计',explicit='designer',stage='design'),['designer'])
        with self.assertRaisesRegex(GateError,'DESIGN_ONLY'):
            route('先设计',explicit='vector',stage='design')
        with self.assertRaisesRegex(ValueError,'READ_ONLY'):
            check_stage(dict(stage='review'),'ppt')

    def test_plot_cli_uses_configured_environment_and_preserves_failure(self):
        import workbench
        configured=self.base/'configured-python.exe';configured.write_bytes(b'test process placeholder')
        args=['workbench.py','--plot-task','request.json','--out','new-output']
        with patch.object(workbench,'PLOT_PY',configured),patch.object(sys,'argv',args),patch.object(workbench.subprocess,'run') as execute:
            execute.return_value.returncode=2
            with self.assertRaises(SystemExit) as stopped:workbench.main()
        self.assertEqual(stopped.exception.code,2)
        self.assertEqual(execute.call_args.args[0][0],str(configured))
        self.assertEqual(execute.call_args.args[0][2:],args[1:])
        self.assertFalse((self.base/'new-output').exists())

    def test_external_task_root_and_protected_child(self):
        external=REPO/'本地输出'/'本轮合成'
        c=dict(authorized_output_roots=[str(external)],protected_paths=[str(external/'原件')])
        self.assertEqual(writable(external/'下一版',c),external/'下一版')
        for p in (external,external/'原件'/'a',REPO/'not_allowed'):
            with self.assertRaises(GateError):writable(p,c)

    def test_scopes_do_not_leak_figure_exception(self):
        profile=resolve_preferences(dict(font_family='Arial'),dict(label_pt=20),dict(leader_policy={'spectrum_A':'none','spectrum_B':'short'}))
        self.assertEqual(profile['scopes']['label_pt'],'project')
        self.assertEqual(profile['scopes']['leader_policy'],'current')
        other=resolve_preferences(dict(font_family='Arial'))
        self.assertNotIn('leader_policy',other['values'])
        self.assertNotIn('label_pt',other['values'])

    def test_verified_group_alias_and_encoding_dont_change_sample_or_unit(self):
        contract=dict(source={'id':'S'},plot_bindings={'x':'time','y':'response'},statistical_n=None)
        old=dict(groups={'sample_A':dict(label='A',color='#804080')},x_title='Time (min)',y_title='Response')
        new=copy.deepcopy(old);new['groups']['sample_A'].update(label='Material A',color='#306080')
        permission=dict(reason='Display name and colour authorized for same sample',
            group_aliases={'sample_A':dict(before='A',after='Material A')},
            group_styles={'sample_A':{'color':dict(before='#804080',after='#306080')}})
        self.assertTrue(require_display_equivalent(contract,old,contract,new,permission))
        changed=copy.deepcopy(contract);changed['plot_bindings']['y']='other_response'
        with self.assertRaises(GateError):require_display_equivalent(contract,old,changed,new,permission)
        new['y_title']='A different unit'
        with self.assertRaises(GateError):require_display_equivalent(contract,old,contract,new,permission)

    def test_number_reuse_and_source_identity(self):
        before=dict(items=[dict(id='ftir_A',label='2b',source_id='S1',placement='main',groups=['A','B'],annotations=['peak'])])
        after=copy.deepcopy(before);after['items'][0]['label']='5f'
        self.assertEqual(compare_content(before,after)['status'],'PASS')
        after['items'][0]['source_id']='different_curve'
        self.assertEqual(compare_content(before,after)['status'],'FAIL')

    def test_no_silent_data_loss_and_reserve_is_retained(self):
        before=dict(items=[dict(id='screen_A',source_id='S1',placement='main',groups=['A','B'])])
        self.assertEqual(compare_content(before,dict(items=[]))['status'],'FAIL')
        after=copy.deepcopy(before);after['items'][0]['placement']='reserve'
        decision=[dict(id='screen_A',fields=['placement'],reason='Author moves selection evidence to reserve')]
        self.assertEqual(compare_content(before,after,decision)['status'],'PASS')
        after['items'][0]['groups']=['A']
        self.assertEqual(compare_content(before,after,decision)['status'],'FAIL')

    def test_frozen_scope_only_reopens_the_named_field(self):
        before=dict(items=[dict(id='figure_A',frozen=True,source_id='S1',placement='main',groups=['A','B'],annotations=['a'])])
        after=copy.deepcopy(before);after['items'][0]['annotations']=['a','label']
        d=[dict(id='figure_A',fields=['annotations'],reopen_scope=['annotations'],reason='One new label requested')]
        self.assertEqual(compare_content(before,after,d)['status'],'PASS')
        after['items'][0]['source_id']='S2'
        self.assertEqual(compare_content(before,after,d)['status'],'FAIL')

    def test_partial_unfreeze_does_not_authorize_whole_figure_deletion(self):
        before=dict(items=[dict(id='F',frozen=True,placement='main')])
        decision=[dict(id='F',action='omit',reason='old request',reopen_scope=['fontsize'])]
        self.assertEqual(compare_content(before,dict(items=[]),decision)['status'],'FAIL')
        decision[0]['reopen_scope']=['omit']
        self.assertEqual(compare_content(before,dict(items=[]),decision)['status'],'PASS')
        new=dict(items=[dict(id='new')])
        self.assertEqual(compare_content(dict(items=[]),new,[dict(id='new',action='add',reason='author')])['status'],'FAIL')

    def test_adopted_parent_is_actually_used_or_verified_derivation_required(self):
        parent=self.base/'manual';parent.write_text('adopted without explanation')
        stale=self.base/'assistant';stale.write_text('old explanation')
        child=self.base/'descendant';child.write_text('adopted with requested small update')
        context=dict(_base=str(self.base),parent=dict(path=str(parent),sha256=sha(parent)))
        require_parent_match(context,parent)
        with self.assertRaisesRegex(ValueError,'NOT_ADOPTED_PARENT'):require_parent_match(context,stale)
        context['verified_descendants']=[dict(artifact=dict(path=child.name,sha256=sha(child)),adopted_parent=context['parent'],
            inheritance_review=dict(reviewer='host',evidence='Compared saved adopted content and allowed changes'))]
        require_parent_match(context,child)
        child.write_text('unreviewed newer modification')
        with self.assertRaises(ValueError):require_parent_match(context,child)

    def test_reviewer_report_does_not_close_unfixed_result(self):
        original=self.base/'before.txt';original.write_text('label hidden')
        f=self.base/'artifact.txt';f.write_text('corrected output')
        r=dict(findings=[dict(id='overlap',location='panel A label',artifact=original.name,sha256=sha(original))],fixes=[],rechecks=[])
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'OPEN')
        r['fixes']=[dict(id='overlap',artifact=f.name,sha256=sha(f))]
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'FIXED_PENDING_RECHECK')
        r['rechecks']=[dict(id='overlap',sha256=sha(f),result='PASS',reviewer='independent',evidence='opened final raster; label visible')]
        self.assertEqual(review_closure(r,self.base)['status'],'CLOSED')
        f.write_text('a new accidental regression')
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'STALE_FIX')

    def test_new_finding_reopens_without_round_limit(self):
        original=self.base/'before';original.write_text('unfixed')
        f=self.base/'artifact';f.write_text('fixed')
        r=dict(findings=[dict(id='F1',artifact=original.name,sha256=sha(original))],fixes=[dict(id='F1',artifact=f.name,sha256=sha(f))],
            rechecks=[dict(id='F1',sha256=sha(f),result='PASS',reviewer='R',evidence='visible')])
        self.assertEqual(review_closure(r,self.base)['status'],'CLOSED')
        r['findings'].append(dict(id='F7',location='newly observed axis clipping'))
        self.assertEqual(review_closure(r,self.base)['unfinished'],1)

    def test_unchanged_file_or_object_cannot_close_as_modified(self):
        old=self.base/'observed';old.write_text('letter hidden')
        same=self.base/'renamed';same.write_bytes(old.read_bytes())
        r=dict(findings=[dict(id='F',artifact=old.name,sha256=sha(old))],
            fixes=[dict(id='F',artifact=same.name,sha256=sha(same))],
            rechecks=[dict(id='F',sha256=sha(same),result='PASS',reviewer='R',evidence='declared checked')])
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'UNCHANGED')
        same.write_text('unrelated changed')
        r['fixes'][0]['sha256']=sha(same);r['rechecks'][0]['sha256']=sha(same)
        r['findings'][0]['object_digest']='actual_same_object'
        r['fixes'][0]['object_digest']='actual_same_object'
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'UNCHANGED_OBJECT')
        del r['fixes'][0]['object_digest']
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'CHANGE_NOT_VERIFIED')
        r['fixes'][0]['object_digest']='actual_corrected_object'
        self.assertEqual(review_closure(r,self.base)['status'],'CLOSED')

    def test_missing_observation_stays_open_but_explicit_false_positive_can_close(self):
        f=self.base/'artifact';f.write_text('unchanged correct output')
        r=dict(findings=[dict(id='F')],fixes=[dict(id='F',artifact=f.name,sha256=sha(f))],
            rechecks=[dict(id='F',sha256=sha(f),result='PASS',reviewer='R',evidence='native inspection')])
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'CHANGE_NOT_VERIFIED')
        r['fixes'][0].update(resolution='no_change_required',reason='Transparent picture does not cover the letter')
        self.assertEqual(review_closure(r,self.base)['status'],'OPEN')
        r['rechecks'][0]['resolution']='no_change_required'
        self.assertEqual(review_closure(r,self.base)['findings'][0]['state'],'CLOSED_NO_CHANGE_REQUIRED')

    def test_cli_explicit_context_is_inherited_by_child(self):
        context=self.base/'context.json'
        context.write_text(json.dumps(dict(schema_version='task-context-0.1',project_id='synthetic',stage='design',
            authorized_output_roots=[str(REPO/'本地输出'/'合成设计')],protected_paths=[])))
        env=dict(os.environ,PYTHONUTF8='1',BAIHE_SCI_TASK_CONTEXT=str(context))
        r=subprocess.run([sys.executable,str(REPO/'工作台/源码/workbench.py'),'--module','ppt','--request-id','must_not_run'],
            env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(r.returncode,2)
        self.assertIn('DESIGN_ONLY',r.stdout)
        self.assertFalse((ROOT/'任务'/'must_not_run').exists())

    def test_new_native_route_records_failure_and_cannot_blindly_replay(self):
        from execution_record import record_call
        from task_status import status
        import uuid
        request=self.base/'task.json';request.write_text('{}')
        identity='新入口失败_'+uuid.uuid4().hex
        def unknown_write():
            folder=self.base/'out';folder.mkdir();(folder/'partial').write_text('partial output')
            raise RuntimeError('native result unknown')
        with self.assertRaisesRegex(RuntimeError,'unknown'):
            record_call('plot',request,self.base/'out',unknown_write,'SYNTHETIC',identity)
        self.assertEqual(status(identity)['status'],'OUTCOME_UNKNOWN_RECONCILE_FIRST')
        with self.assertRaises(FileExistsError):
            record_call('plot',request,self.base/'out',unknown_write,'SYNTHETIC',identity)

    def test_new_entrypoint_receipt_detects_later_file_changes(self):
        from execution_record import record_call
        from task_status import status
        import uuid
        request=self.base/'task.json';request.write_text('{}')
        identity='新入口完成_'+uuid.uuid4().hex
        def write():
            folder=self.base/'out';folder.mkdir();(folder/'native_placeholder.txt').write_text('synthetic contract check only')
            return dict(status='SYNTHETIC_NOT_NATIVE')
        record_call('plot',request,self.base/'out',write,'SYNTHETIC',identity)
        self.assertEqual(status(identity)['status'],'RECORDED_NO_REPLAY')
        (self.base/'out'/'native_placeholder.txt').write_text('manual revision')
        self.assertEqual(status(identity)['status'],'OUTPUT_CHANGED_REVIEW_REQUIRED')


if __name__=='__main__':unittest.main()
