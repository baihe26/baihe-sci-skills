"""Native PPT production for simple approved SceneGraphs, using the existing backend.
Unsupported complex/clip routes remain with the original vector tools.
"""
from paths import *
from ppt_adapter import *
from core import writable,GateError
from coordination import single_writer
from scientific_gate import validate_pack
from processing_ledger import from_scene
from native_connectors import rectangle_connector_plan,bind_native
@single_writer
def produce(scene_path,out,source_png=None):
    scene_path=Path(scene_path).resolve();source_png=Path(source_png).resolve() if source_png else None
    graph=read(scene_path);out=writable(out)
    if out.exists():raise FileExistsError(out)
    consistency=validate_pack(scene_path)
    if graph['asset_refs'] or graph['clipping']:raise GateError('COMPLEX_SCENE_SAFE_LEGACY_HANDOFF_REQUIRED')
    if graph['canvas']['unit']!='px' or graph['canvas']['origin']!='TOP_LEFT':raise GateError('COORDINATE_CONTRACT_UNSUPPORTED')
    import jsonschema
    jsonschema.validate(graph,read(HANDOFF/'schemas/illustrator_scene_graph.schema.json'))
    items=[*graph['objects'],*graph['arrow_objects'],*graph['text_objects']]
    if any(o['geometry']['kind'] not in ('RECT','ELLIPSE','POLYLINE','TEXT') for o in items):raise GateError('COMPLEX_PATH_SAFE_LEGACY_HANDOFF_REQUIRED')
    scale=graph['geometry']['coordinate_transform']['scale_pt_per_px'];w=graph['canvas']['width']*scale;h=graph['canvas']['height']*scale
    connectors=rectangle_connector_plan(graph);binding_results=[]
    out.mkdir(parents=True);target=out/'可编辑示意图.pptx';journal=Journal(out/'恢复日志.jsonl',sha(scene_path))
    save(out/'跨合同一致性检查.json',consistency)
    ensure_owned(target)
    async def run(b):
        await b.create(target);a=connect();p=get_presentation(a,target);p.PageSetup.SlideWidth=w;p.PageSetup.SlideHeight=h
        await b.add_slide();s=p.Slides(1);s.Tags.Add('STUDIO_SLIDE_ID','SCENE')
        for o in sorted(items,key=lambda v:v['z_order']):
            style=graph['style_tokens'][o['style_token']];kind=o['geometry']['kind'];d=o['geometry']['data'];token=journal.begin('SCENE',dict(id=o['id'],geometry=o['geometry']))
            bbox=[o['bbox'][0]*scale,o['bbox'][1]*scale,(o['bbox'][2]-o['bbox'][0])*scale,(o['bbox'][3]-o['bbox'][1])*scale]
            if kind=='TEXT':
                # Data x/y are text anchor and baseline; adapt to native textbox bounding rect.
                size=d['font_size']*scale;text=d['text'];width=max(bbox[2],len(text)*size*.55)
                x=d['x']*scale-(width/2 if d['anchor']=='middle' else width if d['anchor']=='end' else 0)
                await b.object(dict(id=o['id'],type='text',text=text,bbox=[x,(d['y']-d['font_size'])*scale,width,size*1.5],size=size,color=(style['fill'] or '#263238').lstrip('#')))
            elif kind in ('RECT','ELLIPSE'):
                r=await b.object(dict(id=o['id'],type='shape',shape_b='oval' if kind=='ELLIPSE' else 'rectangle',bbox=bbox,text='',fill=(style['fill'] or '#FFFFFF').lstrip('#')))
            else:
                pts=d['points']
                if o['id'] in connectors:
                    q=s.Shapes.AddConnector(1,pts[0][0]*scale,pts[0][1]*scale,pts[-1][0]*scale,pts[-1][1]*scale);q.Name=o['id']
                else:r=await b.call('ppt_build_freeform',dict(slide_index=1,start_x=pts[0][0]*scale,start_y=pts[0][1]*scale,nodes=[dict(segment_type='line',x1=x*scale,y1=y*scale) for x,y in pts[1:]],shape_name=o['id']))
                q=s.Shapes(o['id']);q.Fill.Visible=0
                if d.get('encoding') in ('solid_arrow','dashed_arrow'):q.Line.EndArrowheadStyle=3
                if d.get('encoding')=='inhibition_bar':raise GateError('INHIBITION_REQUIRES_EXPLICIT_BAR_PRIMITIVE')
                b.names[o['id']]={'name':q.Name,'index':None}
            ref=b.names[o['id']];q=s.Shapes(ref['index']) if ref.get('index') else s.Shapes(ref['name']);q.Name=o['id'];q.Tags.Add('STUDIO_ID',o['id'])
            if kind=='TEXT':
                q.TextFrame.TextRange.Font.Name=o.get('font_family','Arial');q.TextFrame.TextRange.Font.NameFarEast='Microsoft YaHei'
                for side in ('MarginLeft','MarginRight','MarginTop','MarginBottom'):setattr(q.TextFrame,side,0)
                q.TextFrame.TextRange.ParagraphFormat.Alignment={'start':1,'middle':2,'end':3}.get(d.get('anchor','start'),1)
            q.Tags.Add('SCIENTIFIC_REFS',','.join(o['scientific_refs']));q.Tags.Add('SCENE_SHA256',sha(scene_path))
            if kind!='TEXT':
                q.Line.Visible=-1 if style.get('stroke') else 0
                if style.get('stroke'):q.Line.ForeColor.RGB=color(style['stroke'].lstrip('#'));q.Line.Weight=style['stroke_width']*scale
                if d.get('dash'):q.Line.DashStyle=4
            journal.commit(token,q.Id)
        # Group semantic owners after constructing exact named primitives. Direct backend owns the operation.
        pending={g['id']:g for g in graph['groups']};links=graph['parent_child'];done=set()
        while pending:
            progress=False
            for gid,g in list(pending.items()):
                kids=[v['child_id'] for v in links if v['parent_id']==gid]
                if any(k in pending for k in kids):continue
                if len(kids)>=2:
                    r=await b.call('ppt_group_shapes',dict(slide_index=1,shape_names=kids))
                    q=next(x for x in s.Shapes if x.Type==6 and all(x.GroupItems.Item(i).Name in kids for i in range(1,x.GroupItems.Count+1)))
                    q.Name=gid;q.Tags.Add('STUDIO_ID',gid)
                elif len(kids)==1:s.Shapes(kids[0]).Tags.Add('SEMANTIC_PARENT',gid)
                pending.pop(gid);done.add(gid);progress=True
            if not progress:raise GateError('SCENE_PARENT_CYCLE')
        binding_results.extend(bind_native(s,connectors,children))
        await b.checkpoint();await b.finish()
    prior=os.getcwd()
    try:os.chdir(BACKEND);result=asyncio.run(with_backend('ykuwai',run,out/'原生调用.jsonl'))
    except BaseException:
        # This exact new target was absent from open decks before create; preserve partial evidence, discard owned unsaved edits.
        for pres in list(connect().Presentations):
            if str(pres.FullName).lower()==str(target).lower():pres.Saved=True;pres.Close()
        raise
    finally:os.chdir(prior)
    verification=native_verify(target,out/'证据')
    elements=from_scene(graph)
    for row in elements['elements']:
        if row['id'] in connectors:row.update(treatment='native_bound_connector',editability='NATIVE_RECTANGLE_ENDPOINTS_MOVE_RESIZE')
    save(out/'元素处理清单.json',elements)
    report=dict(status='NATIVE_COMPLETE_PENDING_EDIT_VISUAL',backend=result,native=verification,scene=source(scene_path),source_png=source(source_png) if source_png else None,
      mode='FAITHFUL_VISIBLE_RECONSTRUCTION_NONBLIND_TEST' if source_png else 'APPROVED_SCENE_PRODUCTION_NO_REDESIGN',physical_size_pt=[w,h],editing='NATIVE_OBJECTS_WITH_EXPLICIT_CONNECTOR_SCOPE',native_bound_connectors=binding_results,free_paths=[a['id'] for a in graph['arrow_objects'] if a['id'] not in connectors],author_acceptance='PENDING')
    save(out/'生产验收.json',report);return report
if __name__=='__main__':print(json.dumps(produce(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None),ensure_ascii=False))
