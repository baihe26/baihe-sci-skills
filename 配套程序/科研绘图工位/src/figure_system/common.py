"""Domain glue around standard file primitives; no custom parser or hash algorithm."""
from pathlib import Path
import hashlib,json,os,tempfile,datetime,sys
ROOT=Path(__file__).resolve().parents[2]
EDITAPLOT=ROOT/'vendor/editaplot'
ORIGIN_PY=Path(os.environ.get('BAIHE_SCI_ORIGIN_PYTHON',sys.executable))
NATURE=ROOT/'vendor/nature_qa'
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write_new(path,payload):
 """Atomic no-clobber publication on this Windows-only MVP, same filesystem."""
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
   json.dump(payload,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
  if os.name!='nt':raise RuntimeError('This MVP uses Windows no-clobber rename semantics')
  os.rename(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def require_hash(path,expected):
 actual=sha(path)
 if actual!=expected:raise ValueError(f'hash mismatch: {Path(path).name}')
 return actual
