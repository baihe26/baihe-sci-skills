from paths import *
from core import writable,GateError,source
import asyncio,zipfile,shutil,contextlib
sys.path.insert(0,str(STUDIO/'03_POC/source'))
from live_studio import with_backend
from manifest_contract import validate
from recovery_journal import Journal,inspect_recovery
from native_finish import connect,get_presentation,find,children,color
from native_audit import shape_state,openxml,snapshot
# Existing import sets an old task TEMP; restore only this process's values.
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'临时文件/TEMP')
def media(path):
    with zipfile.ZipFile(path) as z:return {p:hashlib.sha256(z.read(p)).hexdigest() for p in z.namelist() if p.startswith('ppt/media/') and not p.endswith('/')}
def ensure_owned(path):
    p=writable(path)
    a=connect()
    for pres in a.Presentations:
        if str(pres.FullName).lower()==str(p).lower():raise GateError('TARGET_ALREADY_OPEN_PRESERVE_UNSAVED_CONTENT')
    return a
def native_verify(path,out):
    import native_audit
    native_audit.PROJECT=writable(out)
    return native_audit.verify(path,'原生检查')
def build(manifest_path,out,mode='FAST'):
    m=read(manifest_path);validate(m);out=writable(out)
    if out.exists():raise FileExistsError(out)
    for s in m['slides']:
        for o in s['objects']:
            if o['type']=='picture' and 'source_sha256' in o:source(o['path'],o['source_sha256'])
    out.mkdir(parents=True);target=out/'合成汇报.pptx';journal=Journal(out/'恢复日志.jsonl',digest(m))
    ensure_owned(target)
    async def run(b):
        await b.create(target)
        for slide in m['slides']:
            await b.add_slide()
            for o in slide['objects']:
                token=journal.begin(slide['id'],o);result=await b.object(o)
                if o['type'] in ('connector','group') and o['id'] not in b.names and result.get('shape_name'):
                    b.names[o['id']]={'name':result['shape_name'],'index':result.get('shape_index')}
                journal.commit(token,b.names.get(o['id']))
            # Bind stable identity immediately on the known owned native deck.
            a=connect();p=get_presentation(a,target);s=p.Slides(b.slide);s.Tags.Add('STUDIO_SLIDE_ID',slide['id'])
            for o in slide['objects']:
                ref=b.names.get(o['id'])
                if ref:
                    shape=s.Shapes(ref['index']) if ref.get('index') else s.Shapes(ref['name'])
                    shape.Name=o['id'];shape.Tags.Add('STUDIO_ID',o['id'])
                    if o.get('asset_id'):shape.Tags.Add('ASSET_ID',o['asset_id']);shape.Tags.Add('ASSET_REVISION',o.get('asset_revision','r1'))
                    if o.get('semantic_contract'):shape.Tags.Add('SEMANTIC_SHA256',sha(o['semantic_contract']))
                    if o['type']=='connector':
                        shape.Line.Weight=o.get('line_width_pt',2.2);shape.Line.ForeColor.RGB=color(o.get('line_color','526873'))
            await b.checkpoint();journal.checkpoint(target,b.slide)
        await b.finish()
    prior=os.getcwd()
    try:
        os.chdir(BACKEND);result=asyncio.run(with_backend('ykuwai',run,out/'后端调用.jsonl',mode=mode))
    finally:os.chdir(prior)
    verification=native_verify(target,out/'证据')
    # Explicit editable layers: imported plots stay linked to Origin, authored text remains native.
    save(out/'交付记录.json',dict(status='NATIVE_COMPLETE_PENDING_VISUAL',manifest=source(manifest_path),backend=result,verification=verification,
       editable=dict(outer_text='POWERPOINT_NATIVE',plots='SOURCE_LINKED_ORIGIN_OPJU',svg='EMBEDDED_SVG_NOT_POWERPOINT_OBJECTS'),media=media(target),recovery=inspect_recovery(out/'恢复日志.jsonl',digest(m)),author_acceptance='PENDING'))
    return dict(file=str(target),report=str(out/'交付记录.json'))
def locate(p,slide_id,object_id):
    matches=[]
    for s in p.Slides:
        if s.Tags.Item('STUDIO_SLIDE_ID')==slide_id:
            for v in children(s.Shapes):
                if v.Tags.Item('STUDIO_ID')==object_id:matches.append((s,v))
    if len(matches)!=1:raise GateError('STABLE_OBJECT_ID_MISSING_OR_AMBIGUOUS')
    return matches[0]
def references(path):
    a=ensure_owned(path);p=a.Presentations.Open(str(path),True,False,True);out=[]
    try:
        for s in p.Slides:
            for v in children(s.Shapes):
                asset=v.Tags.Item('ASSET_ID')
                if asset:out.append(dict(reference_id=Path(path).stem+':'+s.Tags.Item('STUDIO_SLIDE_ID')+':'+v.Tags.Item('STUDIO_ID'),deck=str(path),slide_id=s.Tags.Item('STUDIO_SLIDE_ID'),native_slide_id=s.SlideID,object_id=v.Tags.Item('STUDIO_ID'),asset_id=asset,revision=v.Tags.Item('ASSET_REVISION'),semantic_sha256=v.Tags.Item('SEMANTIC_SHA256') or None,object_digest=digest(shape_state(v)),manual_override=False))
    finally:p.Close()
    return out
def local_edit(path,out,slide_id,object_id,operation,value,expected_digest=None):
    """SaveCopyAs new revision. Never writes the input deck or changes unrelated objects."""
    a=ensure_owned(path);out=writable(out)
    if out.exists():raise FileExistsError(out)
    p=a.Presentations.Open(str(path),False,False,True)
    try:
        if p.ReadOnly:raise GateError('DOCUMENT_READ_ONLY')
        s,v=locate(p,slide_id,object_id);before=snapshot(p)
        if expected_digest and digest(shape_state(v))!=expected_digest:raise GateError('MANUAL_CONFLICT')
        if operation=='text':v.TextFrame.TextRange.Text=str(value)
        elif operation=='move':v.Left+=value[0];v.Top+=value[1]
        elif operation=='color':v.Fill.ForeColor.RGB=color(value)
        else:raise GateError('UNAUTHORIZED_LOCAL_OPERATION')
        p.SaveCopyAs(str(out),24);after=snapshot(p)
    finally:
        p.Saved=True;p.Close() # Discard only this owned session's edits, source remains unchanged.
    changed=[]
    for bs,as_ in zip(before['slides'],after['slides']):
        for b,a_ in zip(bs['objects'],as_['objects']):
            if b!=a_:changed.append(b['name'])
    if changed!=[object_id]:raise GateError('UNEXPECTED_LOCAL_SCOPE: '+str(changed))
    return dict(changed=changed,source=source(path),output=source(out),media_unchanged=media(path)==media(out))
def propagate(refs,new_asset,new_revision,out,semantic_contract=None):
    """Actual picture replacement by stable tags, compare native fingerprints before writing."""
    out=writable(out)
    if semantic_contract is None:raise GateError('SCIENTIFIC_SEMANTIC_BINDING_REQUIRED')
    semantic_hash=sha(semantic_contract)
    if any(r.get('semantic_sha256')!=semantic_hash for r in refs):raise GateError('SCIENTIFIC_SEMANTIC_BINDING_CONFLICT')
    if out.exists():raise FileExistsError(out)
    asset_source=source(new_asset);out.mkdir(parents=True);results=[]
    by_deck={}
    for r in refs:by_deck.setdefault(r['deck'],[]).append(r)
    for deck,items in by_deck.items():
        app=ensure_owned(deck);p=app.Presentations.Open(deck,False,False,True);updates=[];conflicts=[];before=snapshot(p)
        try:
            if p.ReadOnly:raise GateError('DOCUMENT_READ_ONLY')
            for r in items:
                s,v=locate(p,r['slide_id'],r['object_id'])
                if v.Tags.Item('SEMANTIC_SHA256')!=semantic_hash:raise GateError('NATIVE_REFERENCE_SEMANTIC_BINDING_CONFLICT')
                if r.get('manual_override') or digest(shape_state(v))!=r['object_digest']:
                    conflicts.append(r['reference_id']);continue
                bbox=[v.Left,v.Top,v.Width,v.Height];z=v.ZOrderPosition
                tags={v.Tags.Name(i):v.Tags.Value(i) for i in range(1,v.Tags.Count+1)}
                v.Delete();q=s.Shapes.AddPicture(str(new_asset),False,True,*bbox);q.Name=r['object_id']
                for k,value in tags.items():q.Tags.Add(k,value)
                q.Tags.Add('ASSET_REVISION',new_revision)
                while q.ZOrderPosition>z:q.ZOrder(3)
                updates.append(r['reference_id'])
            dest=out/(Path(deck).stem+'_新版本.pptx')
            if updates:p.SaveCopyAs(str(dest),24)
            after=snapshot(p)
        finally:p.Saved=True;p.Close()
        results.append(dict(deck=deck,output=str(dest) if updates else None,updated=updates,conflicts=conflicts,source_unchanged=True,unrelated_native_objects_equal=_unrelated_equal(before,after,{r['object_id'] for r in items if r['reference_id'] in updates})))
    save(out/'引用传播结果.json',dict(new_asset=asset_source,semantic_contract=source(semantic_contract),revision=new_revision,results=results))
    from ledger import emit
    emit('REFERENCES_PROPAGATED','SYNTHETIC_INTEGRATION',dict(asset=asset_source,revision=new_revision,semantic_sha256=semantic_hash,results=results))
    return results
def _unrelated_equal(a,b,updated):
    for s,t in zip(a['slides'],b['slides']):
        da={o['name']:o for o in s['objects'] if o['name'] not in updated};db={o['name']:o for o in t['objects'] if o['name'] not in updated}
        if da!=db:return False
    return True
if __name__=='__main__':print(json.dumps(build(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else 'FAST'),ensure_ascii=False))
