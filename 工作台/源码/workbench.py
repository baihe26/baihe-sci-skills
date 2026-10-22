from paths import *
from core import *
import argparse,subprocess
def main():
    p=argparse.ArgumentParser(description='baihe-sci skills：只作图 / 只设计 / 忠实重建 / 按设计生产 / 只PPT。自然语言由当前Codex宿主理解，程序负责合同与原生调用。')
    p.add_argument('intent',nargs='?',default='')
    p.add_argument('--project',default='baihe-sci-local');p.add_argument('--request-id');p.add_argument('--input',action='append',default=[])
    p.add_argument('--module',choices=['plot','designer','vector','ppt']);p.add_argument('--target',choices=['illustrator','ppt'],default='illustrator');p.add_argument('--out');p.add_argument('--bundle');p.add_argument('--spec');p.add_argument('--plan');p.add_argument('--binding');p.add_argument('--scene');p.add_argument('--scene-deck');p.add_argument('--source-image');p.add_argument('--manifest');p.add_argument('--mode',choices=['FAST','LIVE'],default='FAST')
    p.add_argument('--catalog',action='store_true');p.add_argument('--doctor',action='store_true');p.add_argument('--check-protection',action='store_true')
    p.add_argument('--backend',choices=['native','portable'],default='native')
    p.add_argument('--preflight',action='store_true');p.add_argument('--status',action='store_true');p.add_argument('--revise')
    p.add_argument('--compare-images',action='store_true');p.add_argument('--baseline');p.add_argument('--candidate');p.add_argument('--baseline-environment');p.add_argument('--candidate-environment')
    p.add_argument('--verify-trace');p.add_argument('--reference-index',action='append',default=[]);p.add_argument('--propagate')
    p.add_argument('--inspect-project');p.add_argument('--plan-panels');p.add_argument('--verify-delivery');p.add_argument('--artifact')
    a=p.parse_args()
    if a.inspect_project or a.plan_panels or a.verify_delivery:
        operations=(a.inspect_project,a.plan_panels,a.verify_delivery,a.verify_trace,a.reference_index,a.propagate,
                    a.preflight,a.revise,a.compare_images,a.doctor,a.catalog,a.status,a.check_protection)
        if sum(bool(v) for v in operations)!=1 or not a.out or a.module:
            raise GateError('ONE_REVIEW_OPERATION_AND_NEW_OUTPUT_REQUIRED')
        if a.inspect_project:
            from project_intake import intake
            result=intake(a.inspect_project,a.out)
        elif a.plan_panels:
            from project_intake import panel_candidates
            result=panel_candidates(a.plan_panels,a.out)
        else:
            if not a.artifact:raise GateError('FINAL_ARTIFACT_REQUIRED')
            from delivery_review import verify_delivery
            result=verify_delivery(a.verify_delivery,a.artifact,a.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result['status']=='FAIL':sys.exit(2)
        return
    for key in ('bundle','spec','plan','binding','scene','scene_deck','source_image','manifest'):
        if getattr(a,key):setattr(a,key,str(Path(getattr(a,key)).resolve()))
    if a.scene and a.scene_deck:raise GateError('ONE_SCENE_OR_SCENE_DECK_REQUIRED')
    if a.verify_trace or a.reference_index or a.propagate:
        if sum(bool(v) for v in (a.verify_trace,a.reference_index,a.propagate,a.preflight,a.revise,a.compare_images))!=1 or not a.out:raise GateError('ONE_OPERATION_AND_NEW_OUTPUT_REQUIRED')
        out=writable(a.out)
        if out.exists():raise FileExistsError(out)
        if a.verify_trace:
            from provenance import verify_trace
            result=verify_trace(a.verify_trace);save(out/'溯源核对.json',result)
        elif a.reference_index:
            from reference_update import index_references
            refs=[row for deck in a.reference_index for row in index_references(deck)]
            result=dict(status='SAVED_FILE_REFERENCES_INDEXED',references=refs,unsaved_application_state='NOT_INSPECTED_SAVED_FILES_ONLY')
            save(out/'引用索引.json',result)
        else:
            from reference_update import propagate_request
            result=propagate_request(a.propagate,out)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if a.doctor:
        from doctor import report
        print(json.dumps(report(),ensure_ascii=False,indent=2));return
    if a.catalog:
        print((REPO/'文档/能力与验证范围.md').read_text(encoding='utf-8'));return
    if a.check_protection:
        print(json.dumps(dict(status='NO_LOCAL_PROTECTION_BASELINE',guidance='发布包不含原机器的保护快照；先在本地建立源文件哈希基线，不能将缺记录说成保护通过。'),ensure_ascii=False));return
    if a.status:
        if not a.request_id:raise GateError('STATUS_REQUEST_ID_REQUIRED')
        from task_status import status
        print(json.dumps(status(a.request_id),ensure_ascii=False,indent=2));return
    if a.preflight or a.revise or a.compare_images:
        if sum(bool(v) for v in (a.preflight,a.revise,a.compare_images))!=1 or not a.out:raise GateError('ONE_OPERATION_AND_NEW_OUTPUT_REQUIRED')
        if a.preflight:
            from preflight import preflight
            result=preflight(a.out,a.scene,a.spec,a.plan,a.binding)
        elif a.revise:
            if not a.scene:raise GateError('REVISION_SCENE_REQUIRED')
            from refinement import revise
            result=revise(a.scene,a.revise,a.out)
        else:
            if not a.baseline or not a.candidate:raise GateError('IMAGE_COMPARISON_INPUTS_REQUIRED')
            from qa_report import compare_images
            result=compare_images(a.baseline,a.candidate,a.out,a.baseline_environment,a.candidate_environment)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if not a.intent and not a.module:p.print_help();return
    intent=a.intent or dict(plot='只作图',designer='只设计',vector='按已批准SceneGraph生产',ppt='制作PPT')[a.module]
    refs=[*a.input,*[x for x in [a.spec,a.plan,a.binding,a.scene,a.scene_deck,a.source_image,a.manifest] if x]]
    if a.scene:
        from refinement import dependency_paths
        refs.extend(str(p) for p in dependency_paths(a.scene))
    if a.scene_deck:
        from portable_deck import scene_inputs
        from pack_files import dependency_paths
        for item in scene_inputs(a.scene_deck):refs.extend(str(p) for p in dependency_paths(item['scene_path']))
    refs=list(dict.fromkeys(str(Path(p).resolve()) for p in refs))
    if a.bundle:refs.extend(str(p) for p in Path(a.bundle).iterdir() if p.is_file() and p.name in ('figure_spec.json','PLOT_SEMANTICS_CONTRACT.json','plot_data.csv','analysis_manifest.json','observations.csv'))
    modules=route(intent)
    request_id=a.request_id or __import__('uuid').uuid4().hex
    folder=writable(ROOT/'任务'/request_id)
    module=a.module or (modules[0] if len(modules)==1 else None)
    out=writable(a.out or folder/'产物')
    if a.module and a.module not in modules:raise GateError('EXPLICIT_INTENT_MODULE_CONFLICT')
    if a.backend=='portable' and not(module=='vector' and a.target=='ppt' and (a.scene or a.scene_deck)):raise GateError('PORTABLE_BACKEND_ONLY_FOR_APPROVED_VECTOR_PPT')
    if a.scene_deck and a.backend!='portable':raise GateError('SCENE_DECK_REQUIRES_EXPLICIT_PORTABLE_BACKEND')
    if module=='plot' and a.bundle:cmd=[str(PLOT_PY),str(ROOT/'源码/plot_adapter.py'),a.bundle,str(out)]
    elif module=='designer' and all([a.spec,a.plan,a.binding]):cmd=[str(PLOT_PY),str(ROOT/'源码/designer_adapter.py'),a.spec,a.plan,a.binding,str(out)]
    elif module=='vector' and a.scene_deck:cmd=[str(PORTABLE_PY),str(ROOT/'源码/portable_deck.py'),a.scene_deck,str(out)]
    elif module=='vector' and a.scene:cmd=[str(PORTABLE_PY if a.backend=='portable' else PYTHON),str(ROOT/('源码/portable_ppt.py' if a.backend=='portable' else '源码/scene_ppt_adapter.py' if a.target=='ppt' else '源码/vector_adapter.py')),a.scene,str(out),*([a.source_image] if a.source_image else [])]
    elif module=='ppt' and a.manifest:cmd=[str(PYTHON),str(ROOT/'源码/ppt_adapter.py'),a.manifest,str(out),a.mode]
    else:cmd=None
    if cmd:
        if out.exists():raise FileExistsError(out)
        from doctor import require
        if a.backend=='portable':
            from doctor import portable_check
            checked=portable_check()
            if checked['missing']:raise GateError(json.dumps(checked,ensure_ascii=False))
        else:require(module,a.target)
    state=new_task(intent,a.project,refs,request_id)
    if cmd is None:
        save(folder/'待继续.json',dict(status='HOST_CONTRACT_REQUIRED',modules=state['modules'],guidance='由当前Codex按对应旧合同核对科学信息并生成适配输入，禁止猜测。读取SKILL.md按模块继续。',configured_roots={k:str(v) for k,v in dict(plot=PLOT,designer=DESIGN,vector=VECTOR,ppt=STUDIO).items()}))
        print(json.dumps(dict(task_id=state['task_id'],modules=state['modules'],status='HOST_CONTRACT_REQUIRED',task=str(folder)),ensure_ascii=False));return
    from coordination import append_checkpoint
    checkpoint=append_checkpoint(folder/'交接', 'INPUT_BOUND', [r['path'] for r in state['sources']],None,digest(state['sources']),'CLI',semantic_kind='INPUT_CONTRACT_SET_FINGERPRINT_NOT_SCIENTIFIC_TRUTH')
    from recovery_journal import Journal
    journal=Journal(folder/'恢复日志.jsonl',digest(state));token=journal.begin(None,dict(id=module,command=cmd,output=str(out)))
    with (folder/'调用.log').open('x',encoding='utf-8') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONUTF8='1'))
    if r.returncode:
        save(folder/'失败记录.json',dict(returncode=r.returncode,status='FAILED_OR_OUTCOME_UNKNOWN',automatic_retry=False,log=str(folder/'调用.log')));raise RuntimeError('执行未完成，请读取日志；禁止盲目重试 '+str(folder))
    output_manifest=[source(p) for p in sorted(out.rglob('*')) if p.is_file()]
    append_checkpoint(folder/'交接','DESIGN_READY' if module=='designer' else 'PRODUCTION_RECORDED',[r['path'] for r in state['sources']]+[r['path'] for r in output_manifest],checkpoint['sha256'],digest(state['sources']),'CLI',semantic_kind='INPUT_CONTRACT_SET_FINGERPRINT_NOT_SCIENTIFIC_TRUTH')
    journal.commit(token,None);save(folder/'执行回执.json',dict(module=module,backend=a.backend,status='EXECUTED_REVIEW_EVIDENCE',output=str(out),output_manifest=output_manifest,author_acceptance='PENDING'))
    from ledger import emit
    emit('EXECUTION_RECORDED',state['task_id'],dict(module=module,output=str(out),receipt=str(folder/'执行回执.json'),receipt_sha256=sha(folder/'执行回执.json')))
    print(json.dumps(dict(task_id=state['task_id'],module=module,output=str(out),status='EXECUTED_REVIEW_EVIDENCE'),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps(dict(status='SAFE_STOP',reason=str(e)),ensure_ascii=False));sys.exit(2)
