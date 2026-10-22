"""Published or personal engines; configuration and outputs stay local."""
from pathlib import Path
import sys,os,json,hashlib,importlib.util
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
from runtime_config import select_config
CONFIG_FILE,CONFIG_SELECTION=select_config(REPO)
CONFIG=json.loads(CONFIG_FILE.read_text(encoding='utf-8-sig')) if CONFIG_FILE.is_file() else {}
def configured(key,fallback=None):
    value=CONFIG.get(key)
    if not value:return Path(fallback) if fallback is not None else ROOT/'未配置依赖'/key
    p=Path(value).expanduser()
    return (CONFIG_FILE.parent/p).resolve() if not p.is_absolute() else p.resolve()
PLOT=configured('plot_root');DESIGN=configured('designer_root');HANDOFF=configured('designer_contract_root')
VECTOR=configured('vector_root');STUDIO=configured('studio_root');BACKEND=configured('ppt_backend_root')
PYTHON=configured('python',sys.executable);PLOT_PY=configured('plot_python',PYTHON);ORIGIN_PY=configured('origin_python',PLOT_PY)
PORTABLE_PY=configured('portable_python',PYTHON)
VECTOR_HELPERS=configured('illustrator_helpers')
DESKTOP_LOCKS=[ROOT/'桌面生产.lock',*[(Path(p).expanduser() if Path(p).expanduser().is_absolute() else CONFIG_FILE.parent/Path(p).expanduser()).resolve() for p in CONFIG.get('desktop_locks',[])]]
# Legacy engine busy markers remain observe-only: acquiring them could deadlock their own queue.
# A stable per-user D-drive resource is owned by every participating 0.6 writer, across checkouts.
import getpass
_owner_key=hashlib.sha256(getpass.getuser().encode('utf-8')).hexdigest()[:20]
SHARED_WRITER_LOCKS=[Path('D:/baihe-sci共享会话')/_owner_key/'桌面生产.lock',
    *[(Path(p).expanduser() if Path(p).expanduser().is_absolute() else CONFIG_FILE.parent/Path(p).expanduser()).resolve() for p in CONFIG.get('shared_writer_locks',[])]]
TEMP_ROOT=Path(os.environ.get('BAIHE_SCI_TEMP_ROOT',str(ROOT/'临时文件'))).resolve()
if os.name=='nt' and TEMP_ROOT.drive.upper()!='D:':raise ValueError('BAIHE_SCI_TEMP_ROOT必须位于D盘；不回退到系统临时目录。')
for name in ('TEMP','TMP','MPLCONFIGDIR'):
    p=TEMP_ROOT/name;p.mkdir(parents=True,exist_ok=True);os.environ[name]=str(p)
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
