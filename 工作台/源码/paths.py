"""Portable bindings. Native engines stay external; configuration and outputs stay local."""
from pathlib import Path
import sys,os,json,hashlib,importlib.util
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
CONFIG_FILE=Path(os.environ.get('BAIHE_SCI_CONFIG',str(REPO/'baihe-sci.local.json'))).resolve()
CONFIG=json.loads(CONFIG_FILE.read_text(encoding='utf-8-sig')) if CONFIG_FILE.is_file() else {}
def configured(key,fallback=None):
    value=CONFIG.get(key)
    if not value:return Path(fallback) if fallback is not None else ROOT/'未配置依赖'/key
    p=Path(value).expanduser()
    return (CONFIG_FILE.parent/p).resolve() if not p.is_absolute() else p.resolve()
PLOT=configured('plot_root');DESIGN=configured('designer_root');HANDOFF=configured('designer_contract_root')
VECTOR=configured('vector_root');STUDIO=configured('studio_root');BACKEND=configured('ppt_backend_root')
PYTHON=configured('python',sys.executable);PLOT_PY=configured('plot_python',PYTHON);ORIGIN_PY=configured('origin_python',PLOT_PY)
VECTOR_HELPERS=configured('illustrator_helpers')
DESKTOP_LOCKS=[ROOT/'桌面生产.lock',*[(Path(p).expanduser() if Path(p).expanduser().is_absolute() else CONFIG_FILE.parent/Path(p).expanduser()).resolve() for p in CONFIG.get('desktop_locks',[])]]
for name in ('TEMP','TMP','MPLCONFIGDIR'):
    p=ROOT/'临时文件'/name;p.mkdir(parents=True,exist_ok=True);os.environ[name]=str(p)
os.environ['PYTHONDONTWRITEBYTECODE']='1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False)
def load_file(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
