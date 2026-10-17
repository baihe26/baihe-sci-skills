"""Durable action intent and checkpoint bookkeeping; never blind-replay uncertain writes."""
import json,os,uuid,hashlib
from pathlib import Path
from datetime import datetime,timezone
class Journal:
 def __init__(self,path,manifest_sha):self.path=Path(path);self.manifest_sha=manifest_sha;self.path.parent.mkdir(parents=True,exist_ok=True)
 def emit(self,kind,**data):
  ev=dict(timestamp=datetime.now(timezone.utc).isoformat(),kind=kind,manifest_sha256=self.manifest_sha,**data)
  with self.path.open('a',encoding='utf8') as f:f.write(json.dumps(ev,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  return ev
 def begin(self,slide,obj):
  token=uuid.uuid4().hex;self.emit('BEGIN',operation_id=token,slide=slide,semantic_id=obj['id'],parameters=obj);return token
 def commit(self,token,shape_id):self.emit('COMMIT',operation_id=token,powerpoint_shape_id=shape_id)
 def checkpoint(self,path,slide):
  p=Path(path);self.emit('CHECKPOINT',path=str(p),slide=slide,file_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def inspect_recovery(path,expected_manifest):
 events=[];truncated=False
 for line in Path(path).read_text(encoding='utf8').splitlines():
  try:events.append(json.loads(line))
  except ValueError:truncated=True;break
 if any(e.get('manifest_sha256')!=expected_manifest for e in events):raise ValueError('Manifest changed; recovery requires reconciliation')
 pending={};last=None
 for e in events:
  if e['kind']=='BEGIN':pending[e['operation_id']]=e
  elif e['kind']=='COMMIT':pending.pop(e['operation_id'],None)
  elif e['kind']=='CHECKPOINT':last=e
 valid=None
 if last:
  p=Path(last['path']);valid=p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==last['file_sha256']
 return dict(status='OUTCOME_UNKNOWN' if pending or truncated else 'RECORDED',pending=list(pending.values()),truncated_log=truncated,last_checkpoint=last,checkpoint_hash_valid=valid,automatic_retry_allowed=False)
