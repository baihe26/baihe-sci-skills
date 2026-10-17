from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def dump(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def write(p,t):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf-8')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
