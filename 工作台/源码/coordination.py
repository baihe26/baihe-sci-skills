"""Cooperative single native writer and immutable, parent-bound handoffs."""
from paths import ROOT, DESKTOP_LOCKS, save, read, sha, digest, Path
from core import writable, source, GateError
from contextlib import contextmanager
from functools import wraps
import uuid, re


@contextmanager
def exclusive(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = uuid.uuid4().hex
    try:
        with path.open('x', encoding='utf-8') as f:
            f.write(owner)
    except FileExistsError:
        raise GateError('WRITER_BUSY_OR_UNRECONCILED_LOCK: ' + str(path))
    try:
        yield
    finally:
        # Never remove a lock replaced by another process or a human.
        if path.is_file() and path.read_text(encoding='utf-8') == owner:
            path.unlink()


def single_writer(function):
    @wraps(function)
    def call(*args, **kwargs):
        own = ROOT / '桌面生产.lock'
        for path in DESKTOP_LOCKS:
            if path.exists():
                raise GateError('DESKTOP_BUSY: ' + str(path))
        with exclusive(own):
            for path in DESKTOP_LOCKS:
                if path != own and path.exists():
                    raise GateError('DESKTOP_BUSY: ' + str(path))
            return function(*args, **kwargs)
    return call


def append_checkpoint(folder, stage, inputs, expected_parent, semantic_sha256, writer, semantic_kind='HOST_DECLARED'):
    """Host calls this at real milestones. No synthesized review or automatic rerun."""
    folder = writable(folder)
    if stage not in ('INPUT_BOUND', 'DESIGN_READY', 'NATIVE_RECORDED', 'PRODUCTION_RECORDED', 'REVIEW_RECORDED'):
        raise GateError('UNKNOWN_CHECKPOINT_STAGE')
    if not re.fullmatch(r'[0-9a-f]{64}', semantic_sha256) or not writer:
        raise GateError('CHECKPOINT_IDENTITY_REQUIRED')
    with exclusive(folder / '交接写入.lock'):
        paths = sorted(folder.glob('交接_*.json'))
        parent = sha(paths[-1]) if paths else None
        if parent != expected_parent:
            raise GateError('CHECKPOINT_PARENT_CONFLICT_PRESERVE_BOTH')
        chain_parent = None
        for number, previous in enumerate(paths, 1):
            row = read(previous)
            if row['expected_parent'] != chain_parent or row['revision'] != number:
                raise GateError('CHECKPOINT_HISTORY_CONFLICT')
            for ref in row['inputs']:
                source(ref['path'], ref['sha256'])
            chain_parent = sha(previous)
        row = dict(schema_version='handoff-0.1', revision=len(paths)+1, stage=stage,
                   expected_parent=parent, semantic_sha256=semantic_sha256, writer=writer,
                   semantic_kind=semantic_kind,
                   inputs=[source(p) for p in inputs], automatic_retry=False,
                   scientific_review='PENDING', author_acceptance='PENDING')
        destination = folder / ('交接_%06d.json' % row['revision'])
        save(destination, row)
        return dict(path=str(destination), sha256=sha(destination), revision=row['revision'])
