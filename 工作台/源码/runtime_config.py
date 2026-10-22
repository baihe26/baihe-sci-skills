"""One selection rule for all entrypoints; no configuration writes or fallback on errors."""
from pathlib import Path
import os


def select_config(repo, environ=None):
    env = os.environ if environ is None else environ
    repo = Path(repo).resolve()
    explicit = env.get('BAIHE_SCI_CONFIG')
    if explicit:
        return Path(explicit).expanduser().resolve(), 'EXPLICIT_ENVIRONMENT'
    for name, reason in (('baihe-sci.local.json', 'EXISTING_PERSONAL'),
                         ('baihe-sci.public.local.json', 'PUBLIC_DISTRIBUTION')):
        path = repo / name
        if path.is_file():
            return path, reason
    return repo / 'baihe-sci.local.json', 'NOT_CONFIGURED'
