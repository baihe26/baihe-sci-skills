"""Check adopted content and review closure against actual saved artifacts."""
from pathlib import Path
import re
from paths import read, sha, digest, save
from core import GateError, writable
from task_context import resolve_path


def _unique(rows, kind):
    index = {}
    for row in rows:
        key = row.get('id')
        if not key or key in index:
            raise GateError('DUPLICATE_OR_MISSING_' + kind.upper() + '_ID')
        index[key] = row
    return index


def compare_content(before, after, decisions=()):
    """IDs follow the data, never a re-used figure letter. No automatic deletion."""
    old = _unique(before.get('items', []), 'content')
    new = _unique(after.get('items', []), 'content')
    permitted = _unique(decisions, 'decision')
    changes, findings = [], []
    for identity, row in old.items():
        current = new.get(identity)
        decision = permitted.get(identity, {})
        if current is None:
            changes.append(dict(id=identity, kind='removed'))
            if decision.get('action') not in ('omit', 'deduplicate') or not decision.get('reason'):
                findings.append(dict(id=identity, kind='UNACCOUNTED_CONTENT', message='原来采用的数据或标注没有交代去向。'))
            if row.get('frozen') and decision.get('action') not in decision.get('reopen_scope',[]):
                findings.append(dict(id=identity, kind='FROZEN_CONTENT_REMOVED'))
            continue
        for field in ('source_id', 'groups', 'annotations', 'content_digest', 'placement'):
            if row.get(field) == current.get(field):
                continue
            changes.append(dict(id=identity, kind='changed', field=field,
                                before=row.get(field), after=current.get(field)))
            # Presentation labels are deliberately absent: new numbering is not new data.
            if row.get('frozen') and field not in decision.get('reopen_scope', []):
                findings.append(dict(id=identity, kind='FROZEN_SCOPE_CHANGED', field=field))
            if field in ('source_id', 'groups', 'annotations', 'placement'):
                if field not in decision.get('fields', []) or not decision.get('reason'):
                    findings.append(dict(id=identity, kind='UNEXPLAINED_CONTENT_CHANGE', field=field))
    for identity in new.keys() - old.keys():
        changes.append(dict(id=identity, kind='added'))
        decision = permitted.get(identity, {})
        if decision.get('action') != 'add' or not decision.get('reason'):
            findings.append(dict(id=identity, kind='UNAPPROVED_CONTENT_ADDITION'))
    for identity,current in new.items():
        if current.get('placement') not in ('main','supplement','reserve','omitted'):
            findings.append(dict(id=identity,kind='CONTENT_DESTINATION_REQUIRED'))
    return dict(status='FAIL' if findings else 'PASS', changes=changes, findings=findings,
                scope='声明的稳定内容身份与去向；不代替图面及科学审查。')


def review_closure(request, base):
    """A sent report or self-declared fixed flag is not a verified resolution."""
    findings = _unique(request.get('findings', []), 'finding')
    fixes = _unique(request.get('fixes', []), 'fix')
    reviews = _unique(request.get('rechecks', []), 'recheck')
    result = []
    for identity, finding in findings.items():
        fix, review = fixes.get(identity), reviews.get(identity)
        state, reason = 'OPEN', '尚未提供修改后的文件及对应复验。'
        if fix:
            state = 'FIXED_PENDING_RECHECK'
            artifact = resolve_path(fix.get('artifact', ''), base)
            resolution=fix.get('resolution','modified')
            if resolution not in ('modified','no_change_required'):
                raise GateError('REVIEW_RESOLUTION_UNSUPPORTED')
            if not artifact.is_file() or sha(artifact) != fix.get('sha256'):
                state, reason = 'STALE_FIX', '修复记录与当前文件不一致。'
            elif resolution=='no_change_required':
                if (fix.get('reason') and review and review.get('sha256')==fix['sha256']
                    and review.get('result')=='PASS' and review.get('reviewer') and review.get('evidence')
                    and review.get('resolution')=='no_change_required'):
                    state,reason='CLOSED_NO_CHANGE_REQUIRED','复验明确认定无需改动：'+fix['reason']
                else:
                    state,reason='OPEN','无需修改的处置须说明原因，并有针对当前文件的明确复验。'
            elif not finding.get('artifact') or not re.fullmatch(r'[0-9a-f]{64}',str(finding.get('sha256',''))):
                state,reason='CHANGE_NOT_VERIFIED','未绑定发现问题时的文件版本，无法确认已实际修改。'
            elif finding['sha256']==fix['sha256']:
                state,reason='UNCHANGED','当前文件与发现问题时内容相同，不能登记为已修复。'
            elif finding.get('object_digest') and finding['object_digest']==fix.get('object_digest'):
                state,reason='UNCHANGED_OBJECT','问题对象仍与发现时相同，文件其它部分变化不能算此处已修复。'
            elif finding.get('object_digest') and not fix.get('object_digest'):
                state,reason='CHANGE_NOT_VERIFIED','发现记录绑定了具体对象，修复记录须补该对象的当前指纹。'
            elif review and review.get('sha256') == fix['sha256'] and review.get('result') == 'PASS' and review.get('reviewer') and review.get('evidence'):
                state, reason = 'CLOSED', '已记录对当前修复文件的具体复验。'
            else:
                reason = '已改文件，但仍缺对应当前版本的复验。'
        if finding.get('disposition') == 'needs_author':
            if not finding.get('question') or not finding.get('source_location'):
                state, reason = 'OPEN', '待作者确认必须写清具体事实和来源位置。'
            elif state not in ('CLOSED','CLOSED_NO_CHANGE_REQUIRED'):
                state, reason = 'NEEDS_AUTHOR', finding['question']
        result.append(dict(id=identity, state=state, reason=reason, location=finding.get('location')))
    unknown = (set(fixes) | set(reviews)) - set(findings)
    if unknown:
        raise GateError('REVIEW_UNKNOWN_FINDING: ' + ','.join(sorted(unknown)))
    unresolved = [row for row in result if row['state'] not in ('CLOSED','CLOSED_NO_CHANGE_REQUIRED')]
    return dict(status='OPEN' if unresolved else 'CLOSED', findings=result,
                unfinished=len(unresolved), review_scope='核对记录与当前文件的一致性；不冒充独立视觉或科学评审。')


def check_request(request_path, out=None):
    path = Path(request_path).resolve()
    request = read(path)
    result = {}
    if 'before' in request and 'after' in request:
        result['content'] = compare_content(request['before'], request['after'], request.get('decisions', []))
    if 'findings' in request:
        result['review'] = review_closure(request, path.parent)
    if not result:
        raise GateError('REVISION_COMPARISON_OR_REVIEW_REQUIRED')
    result['status'] = 'FAIL' if any(r['status'] == 'FAIL' for r in result.values()) else 'OPEN' if any(r['status'] == 'OPEN' for r in result.values()) else 'PASS'
    if out:
        folder = writable(out)
        if folder.exists():
            raise FileExistsError(folder)
        save(folder / '内容去向与审改核对.json', result)
    return result
