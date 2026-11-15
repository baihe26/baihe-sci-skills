"""Small, opt-in task context. Project decisions never become global defaults."""
from pathlib import Path
import os
from paths import read, sha, digest


def load_context(path=None):
    path = path or os.environ.get('BAIHE_SCI_TASK_CONTEXT')
    if not path:
        return None
    path = Path(path).resolve()
    context = read(path)
    if context.get('schema_version') != 'task-context-0.1':
        raise ValueError('TASK_CONTEXT_VERSION_REQUIRED')
    if not str(context.get('project_id', '')).strip():
        raise ValueError('TASK_PROJECT_REQUIRED')
    stages = ('understand', 'design', 'produce', 'revise', 'review', 'package')
    if context.get('stage') not in stages:
        raise ValueError('TASK_STAGE_REQUIRED')
    context = dict(context, _base=str(path.parent), _file=str(path), _sha256=sha(path))
    for field in ('authorized_output_roots', 'protected_paths'):
        values = context.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError('TASK_PATH_LIST_INVALID: ' + field)
        context[field] = [str(resolve_path(v, path.parent)) for v in values]
    for value in context.get('authorized_output_roots', []):
        root = Path(value)
        if root == Path(root.anchor) or (os.name == 'nt' and root.drive.upper() != 'D:'):
            raise ValueError('TASK_OUTPUT_REQUIRES_BOUNDED_D_DIRECTORY')
    parent = context.get('parent')
    if parent:
        p = resolve_path(parent['path'], path.parent)
        if not p.is_file() or sha(p) != parent.get('sha256'):
            raise ValueError('MANUAL_PARENT_CHANGED: 以当前人工文件重新接入，不能沿旧父本覆盖。')
        context['parent'] = dict(parent, path=str(p))
        context['protected_paths'].append(str(p))
    if context.get('author_profile'):
        profile_path=resolve_path(context['author_profile'],path.parent)
        profile=read(profile_path)
        if profile.get('schema_version')!='author-preferences-0.1' or not isinstance(profile.get('defaults'),dict):
            raise ValueError('AUTHOR_PROFILE_INVALID')
        context['resolved_preferences']=resolve_preferences(profile['defaults'],context.get('project_preferences'),context.get('preferences'))
        context['author_profile_source']=dict(path=str(profile_path),sha256=sha(profile_path))
    return context


def resolve_path(path, base):
    p = Path(path).expanduser()
    return (Path(base) / p).resolve() if not p.is_absolute() else p.resolve()


def output_allowed(path, context):
    p = Path(path).resolve()
    # A parent directory of protected material is also unsafe as an output root.
    for item in context.get('protected_paths', []):
        protected = Path(item).resolve()
        if p == protected or p.is_relative_to(protected) or protected.is_relative_to(p):
            return False
    return any(p.is_relative_to(Path(root).resolve()) for root in context.get('authorized_output_roots', []))


def check_stage(context, module):
    if not context:
        return
    allowed = context.get('modules')
    if allowed is not None and module not in allowed:
        raise ValueError('TASK_MODULE_OUTSIDE_SCOPE')
    if context['stage'] in ('understand', 'review'):
        raise ValueError('READ_ONLY_TASK_NO_PRODUCTION')
    if context['stage'] == 'design' and module != 'designer':
        raise ValueError('DESIGN_ONLY_NO_PRODUCTION')


def require_parent_match(context,artifact):
    """For an edit to an existing artifact, use the adopted parent or bound descendant."""
    if not context or not context.get('parent'):return
    candidate=Path(artifact).resolve();parent=Path(context['parent']['path']).resolve()
    if not parent.is_file() or sha(parent)!=context['parent']['sha256']:raise ValueError('MANUAL_PARENT_CHANGED')
    if candidate==parent:
        return
    for row in context.get('verified_descendants',[]):
        ref=row.get('artifact',{});base=context['_base']
        p=resolve_path(ref.get('path',''),base)
        if candidate!=p:continue
        expected=row.get('adopted_parent',{})
        if (resolve_path(expected.get('path',''),base)==parent and expected.get('sha256')==context['parent']['sha256']
            and p.is_file() and sha(p)==ref.get('sha256') and row.get('inheritance_review',{}).get('reviewer')
            and row['inheritance_review'].get('evidence')):return
    raise ValueError('ARTIFACT_IS_NOT_ADOPTED_PARENT: 输入不是本轮人工父本，也没有已核继承关系，不能用旧助手稿继续修改。')


def resolve_preferences(author=None, project=None, current=None):
    """Host supplies only applicable scopes; no journal/figure/sample defaults."""
    result, origins = {}, {}
    for scope, values in (('author', author), ('project', project), ('current', current)):
        for key, value in (values or {}).items():
            result[key] = value
            origins[key] = scope
    return dict(values=result, scopes=origins, fingerprint=digest(dict(values=result, scopes=origins)))
