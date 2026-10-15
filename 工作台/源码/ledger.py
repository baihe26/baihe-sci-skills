"""One append-only coordination ledger; native contracts remain authoritative sidecars."""
from paths import *
import datetime,uuid
def emit(kind,task_id,payload):
    p=ROOT/'共同记录/事件台账.jsonl';p.parent.mkdir(exist_ok=True)
    event=dict(event_id=uuid.uuid4().hex,timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind=kind,task_id=task_id,payload=payload)
    with p.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    return event
def events():
    p=ROOT/'共同记录/事件台账.jsonl'
    return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()] if p.exists() else []
def register_asset(task_id,asset_id,revision,files,semantic_contract,style_version,parent=None,editability='SOURCE_LINKED',human_override=None):
    if any(e['kind']=='ASSET_REVISION' and e['payload']['asset_id']==asset_id and e['payload']['revision']==revision for e in events()):raise ValueError('IMMUTABLE_ASSET_REVISION_EXISTS')
    def ref(p):return dict(path=str(Path(p)),sha256=sha(p))
    return emit('ASSET_REVISION',task_id,dict(asset_id=asset_id,revision=revision,parent_revision=parent,files=[ref(p) for p in files],semantic_contract=ref(semantic_contract),style_version=style_version,editability=editability,human_override=human_override,validation=dict(technical='SEE_REFERENCED_REPORTS',scientific_review='PENDING',author_acceptance='PENDING')))
