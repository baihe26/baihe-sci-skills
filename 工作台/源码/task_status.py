"""Read-only reconciliation: source/output changes and unknown writes never auto-replay."""
from paths import ROOT,Path,read,sha,digest,save
from core import writable,GateError
from recovery_journal import inspect_recovery


def status(request_id):
    folder=writable(ROOT/'任务'/request_id)
    if folder.parent!=ROOT/'任务':raise GateError('INVALID_TASK_ID')
    state=read(folder/'任务记录.json');source_conflicts=[]
    for ref in state['sources']:
        p=Path(ref['path'])
        if not p.is_file() or sha(p)!=ref['sha256']:source_conflicts.append(ref['path'])
    receipt_path=folder/'执行回执.json';receipt=read(receipt_path) if receipt_path.is_file() else None
    output_conflicts=[]
    if receipt:
        for ref in receipt.get('output_manifest',[]):
            p=Path(ref['path'])
            if not p.is_file() or sha(p)!=ref['sha256']:output_conflicts.append(ref['path'])
    journal_path=folder/'恢复日志.jsonl'
    journal=inspect_recovery(journal_path,digest(state)) if journal_path.is_file() else None
    if source_conflicts:result='SOURCE_CONFLICT'
    elif output_conflicts:result='OUTPUT_CHANGED_REVIEW_REQUIRED'
    elif journal and journal['status']=='OUTCOME_UNKNOWN':result='OUTCOME_UNKNOWN_RECONCILE_FIRST'
    elif receipt:result='RECORDED_NO_REPLAY' if receipt.get('output_manifest') else 'RECEIPT_PRESENT_UNVERIFIED_OUTPUT'
    elif (folder/'失败记录.json').is_file():result='FAILED_RECONCILE_FIRST'
    elif (folder/'待继续.json').is_file():result='HOST_CONTRACT_REQUIRED'
    else:result='NOT_EXECUTED_OR_INTERRUPTED_RECONCILE_FIRST'
    return dict(task_id=request_id,status=result,source_conflicts=source_conflicts,output_conflicts=output_conflicts,
                journal=journal,automatic_retry=False,receipt=receipt,author_acceptance='PENDING')
