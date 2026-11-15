"""Reuse the existing recovery journal for new normal entrypoints."""
from pathlib import Path
from paths import ROOT, read, save, digest
from core import source, writable, new_task
from recovery_journal import Journal


def file_dependencies(request_path):
    path=Path(request_path).resolve();result={path}
    def visit(value):
        if isinstance(value,dict):
            if isinstance(value.get('path'),str) and value.get('sha256'):
                p=Path(value['path']);p=p if p.is_absolute() else path.parent/p
                source(p,value['sha256']);result.add(p.resolve())
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(read(path))
    return sorted(result)


def record_call(module,request_path,out,call,project_id,request_id=None,context=None):
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    refs=file_dependencies(request_path)
    if context:
        refs.append(Path(context['_file']))
        if context.get('parent'):refs.append(Path(context['parent']['path']))
    state=new_task('按已核对任务执行并保存恢复记录',project_id,refs,request_id,[module],context)
    folder=ROOT/'任务'/state['task_id']
    journal=Journal(folder/'恢复日志.jsonl',digest(state))
    token=journal.begin(None,dict(id=module,request=str(request_path),output=str(out)))
    try:
        result=call()
        manifest=[source(p) for p in sorted(out.rglob('*')) if p.is_file()]
        if not manifest:raise RuntimeError('EXECUTION_OUTPUT_MISSING')
        for ref in state['sources']:source(ref['path'],ref['sha256'])
        journal.commit(token,None)
        save(folder/'执行回执.json',dict(module=module,status=result.get('status'),output_manifest=manifest,
            output=str(out),author_acceptance='PENDING'))
    except Exception as exc:
        save(folder/'失败记录.json',dict(status='FAILED_OR_OUTCOME_UNKNOWN',reason=str(exc),automatic_retry=False))
        raise
    return dict(result,task_id=state['task_id'])
