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
    p.add_argument('--task-context',help='本轮阶段、人工父本、可输出根与保护范围；由宿主按现有授权生成。')
    p.add_argument('--check-revision',help='检查稳定小图/数据去向及审阅问题是否已落实。')
    p.add_argument('--inspect-microscopy',help='只读提取原PPT显微图的对象、裁剪及显示处理。')
    p.add_argument('--audit-presentation',help='实际保存PPT的组缩放、字号继承及遮挡候选。')
    p.add_argument('--profile',help='仅本轮启用的视觉偏好JSON。')
    p.add_argument('--verify-package',help='按本版面板及配套角色核对交付包。')
    p.add_argument('--write-notes',help='按已核对来源写备注，新副本保留人工修改。')
    p.add_argument('--vector-capabilities',help='为给定SceneGraph检查当前后端是否支持所需效果。')
    p.add_argument('--plot-task',help='真实表或已有Origin项目的显式接入任务。')
    p.add_argument('--execute-plot',action='store_true',help='执行已明确映射的数据图任务；否则只核对。')
    p.add_argument('--edit-ppt',help='沿已保存人工PPT局部改字、字体或位置，不占原生会话。')
    a=p.parse_args()
    operations=(a.inspect_microscopy,a.check_revision,a.audit_presentation,a.verify_package,a.write_notes,a.vector_capabilities,
                a.plot_task,a.edit_ppt,a.inspect_project,a.plan_panels,a.verify_delivery,a.verify_trace,a.reference_index,a.propagate,
                a.preflight,a.revise,a.compare_images,a.doctor,a.catalog,a.status,a.check_protection)
    if sum(bool(v) for v in operations)>1:raise GateError('ONE_OPERATION_REQUIRED')
    if a.execute_plot and not a.plot_task:raise GateError('EXECUTE_PLOT_REQUIRES_TASK')
    # Match the legacy plot route: the configured plotting interpreter owns its
    # template dependencies; an Office coordinator need not install them too.
    if a.plot_task and Path(sys.executable).resolve()!=PLOT_PY.resolve():
        if not PLOT_PY.is_file():raise GateError('CONFIGURED_PLOT_PYTHON_MISSING')
        result=subprocess.run([str(PLOT_PY),str(Path(__file__).resolve()),*sys.argv[1:]],
                              env=dict(os.environ,PYTHONUTF8='1'))
        sys.exit(result.returncode)
    from task_context import load_context, check_stage, require_parent_match, resolve_path
    if a.task_context:os.environ['BAIHE_SCI_TASK_CONTEXT']=str(Path(a.task_context).resolve())
    context=load_context()
    if context:
        if a.project!='baihe-sci-local' and a.project!=context['project_id']:raise GateError('TASK_PROJECT_CONFLICT')
        a.project=context['project_id']
        if context['stage'] in ('understand','review') and (a.revise or a.propagate or a.write_notes or a.edit_ppt or a.execute_plot):raise GateError('READ_ONLY_TASK_NO_ARTIFACT_REVISION')
    if a.audit_presentation or a.verify_package or a.write_notes or a.edit_ppt or a.vector_capabilities or a.plot_task:
        if a.module:raise GateError('OPERATION_ALREADY_SELECTS_MODULE')
        if a.audit_presentation:
            from delivery_review import audit_presentation
            result=audit_presentation(a.audit_presentation,read(a.profile) if a.profile else None,a.out)
        elif a.verify_package:
            from delivery_package import verify_package
            result=verify_package(a.verify_package,a.out)
        elif a.write_notes:
            check_stage(context,'ppt')
            if not a.out:raise GateError('NEW_NOTES_OUTPUT_REQUIRED')
            note_request=read(a.write_notes)
            require_parent_match(context,resolve_path(note_request['artifact']['path'],Path(a.write_notes).resolve().parent))
            from delivery_package import write_notes
            result=write_notes(a.write_notes,a.out)
        elif a.edit_ppt:
            check_stage(context,'local')
            if not a.out:raise GateError('NEW_PPT_REVISION_OUTPUT_REQUIRED')
            from ppt_local_patch import edit_ppt
            result=edit_ppt(a.edit_ppt,a.out)
        elif a.vector_capabilities:
            from design_styles import capability_route
            scene=Path(a.vector_capabilities).resolve()
            backend='portable' if a.backend=='portable' else 'illustrator' if a.target=='illustrator' else 'ppt_native'
            result=capability_route(read(scene),backend,(scene.parent/'retained_assets.json').is_file())
        else:
            if a.execute_plot:check_stage(context,'plot')
            if not a.out:raise GateError('NEW_PLOT_TASK_OUTPUT_REQUIRED')
            plot_request=read(a.plot_task)
            if plot_request.get('operation')=='revise_origin':
                require_parent_match(context,resolve_path(plot_request['parent_origin']['path'],Path(a.plot_task).resolve().parent))
            from plot_adapter import run_plot_task
            if a.execute_plot:
                from plot_sources import inspect_plot_task
                inspect_plot_task(a.plot_task)
                if read(a.plot_task)['operation']=='render_table':
                    from plot_runtime import prepare_native
                    prepare_native(a.plot_task)
                from execution_record import record_call
                result=record_call('plot',a.plot_task,a.out,lambda:run_plot_task(a.plot_task,a.out,execute=True),
                                   a.project,a.request_id,context)
            else:result=run_plot_task(a.plot_task,a.out,execute=False)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result.get('status') in ('FAIL','PACKAGE_REQUIRES_REPAIR','EXPLICIT_HANDOFF_REQUIRED'):sys.exit(2)
        return
    if a.inspect_microscopy:
        if any((a.module,a.check_revision,a.inspect_project,a.plan_panels,a.verify_delivery,a.propagate,a.revise)):
            raise GateError('ONE_OPERATION_REQUIRED')
        from microscopy_sources import inspect_request
        print(json.dumps(inspect_request(a.inspect_microscopy,a.out),ensure_ascii=False,indent=2));return
    if a.check_revision:
        if any((a.module,a.inspect_project,a.plan_panels,a.verify_delivery,a.propagate,a.revise)):
            raise GateError('ONE_OPERATION_REQUIRED')
        from revision_checks import check_request
        result=check_request(a.check_revision,a.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result['status']!='PASS':sys.exit(2)
        return
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
            require_parent_match(context,a.scene)
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
    modules=route(intent,a.module,context.get('stage') if context else None)
    request_id=a.request_id or __import__('uuid').uuid4().hex
    folder=writable(ROOT/'任务'/request_id)
    module=a.module or (modules[0] if len(modules)==1 else None)
    if module:check_stage(context,module)
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
    state=new_task(intent,a.project,refs,request_id,modules,context)
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
