"""SceneGraph -> SVG through frozen primitives -> existing Illustrator bridge/export helpers.
No redraw of scientific images; source-guided reconstructions require a separately authored scene.
"""
from paths import *
from core import writable,source,GateError
import html,xml.etree.ElementTree as ET,subprocess
from coordination import single_writer
def scene_svg(graph):
    # Keep group identity and hierarchy. Reject unsupported assets rather than flattening them.
    from designer_adapter import replay
    r=replay();w,h=graph['canvas']['width'],graph['canvas']['height']
    if graph['canvas']['origin']!='TOP_LEFT' or graph['canvas']['unit']!='px':raise GateError('COORDINATE_CONTRACT_UNSUPPORTED_USE_LEGACY_HANDOFF')
    if graph['asset_refs'] or graph['clipping']:raise GateError('ASSET_OR_CLIP_REQUIRES_LEGACY_PRODUCTION_ADAPTER')
    objects={o['id']:o for key in ('objects','arrow_objects','text_objects') for o in graph[key]}
    groups={g['id']:g for g in graph['groups']};parents={}
    for link in graph['parent_child']:
        if link['child_id'] in parents:raise GateError('MULTIPLE_PARENTS')
        parents[link['child_id']]=link['parent_id']
    def emit(key,trail=()):
        if key in trail:raise GateError('PARENT_CYCLE')
        if key in groups:
            children=[k for k in [*groups,*objects] if parents.get(k)==key]
            return '<g id="'+html.escape(key)+'">'+''.join(emit(k,trail+(key,)) for k in children)+'</g>'
        o=objects[key];s=graph['style_tokens'][o['style_token']];kind=o['geometry']['kind'];data=o['geometry']['data']
        if kind not in ('RECT','ELLIPSE','PATH','POLYLINE','TEXT'):raise GateError('GEOMETRY_USE_LEGACY_HANDOFF: '+kind)
        element=dict(id=key,owner=o.get('group_id'),kind=kind,data=data,fill=s.get('fill') or 'none',stroke=s.get('stroke') or 'none',stroke_width=s.get('stroke_width',0),dash=data.get('dash'))
        body=r.element_svg(element)
        if key in {v['id'] for v in graph['arrow_objects']}:
            p=r.arrow_paths(data['points'],data['encoding'])
            if p:body+='<polyline points="'+' '.join(f'{x},{y}' for x,y in p)+'" fill="none" stroke="'+s['stroke']+'" stroke-width="2.2"/>'
        return '<g id="'+html.escape(key)+'_semantic">'+body+'</g>'
    allids=[*groups,*objects]
    if any(p not in groups for p in parents.values()):raise GateError('UNKNOWN_PARENT')
    scale=graph['geometry']['coordinate_transform']['scale_pt_per_px']
    output=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*scale}pt" height="{h*scale}pt" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="white"/>'
    output+=''.join(emit(k) for k in allids if k not in parents)+'</svg>'
    return output
@single_writer
def produce(scene_path,out,source_image=None,mode='approved_design'):
    scene_path=Path(scene_path).resolve();source_image=Path(source_image).resolve() if source_image else None
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    graph=read(scene_path)
    from scientific_gate import validate_pack
    consistency=validate_pack(scene_path)
    import jsonschema
    jsonschema.validate(graph,read(HANDOFF/'schemas/illustrator_scene_graph.schema.json'))
    if mode=='faithful_reconstruction' and not source_image:raise GateError('SOURCE_IMAGE_REQUIRED')
    out.mkdir(parents=True);svg=out/'施工输入.svg'
    save(out/'跨合同一致性检查.json',consistency)
    from processing_ledger import from_scene
    save(out/'元素处理清单.json',from_scene(graph))
    subprocess.run([str(PLOT_PY),__file__,'--svg-only',str(scene_path),str(svg)],check=True,env=dict(os.environ,PYTHONUTF8='1'))
    save(out/'生产来源.json',dict(scene=source(scene_path),mode=mode,source_image=source(source_image) if source_image else None,
      scientific_binding_sidecar='required alongside SceneGraph',redesign=False,limits=['仅矩形/椭圆/路径/文字/关系与层级映射；复杂资产和clip安全转交旧入口','源图语义由宿主根据可见内容记录，遮挡与不清楚的字不猜测']))
    from illustrator_native import production
    first=production(svg,scene_path,out)
    # A fresh Python client attaches to the existing Illustrator instance and reopens the saved AI.
    # This proves saved-file readback, not a full restart of Illustrator or a human acceptance.
    with (out/'独立客户端调用.log').open('x',encoding='utf-8') as log:
        subprocess.run([str(PYTHON),str(ROOT/'源码/illustrator_native.py'),'reopen',str(scene_path),str(out)],check=True,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONUTF8='1'))
    reopened=read(out/'独立客户端重开/原生重开检查.json')
    result=dict(first=first['before']['counts'],reopened=reopened['snapshot']['counts'],checks=first['checks'],reopen_checks=reopened['checks'],closed_owned_only=True,visual='PENDING',semantic_edit_test='PENDING',author_acceptance='PENDING',production_status='NATIVE_SAVED_REOPENED')
    save(out/'原生生产检查.json',result);return result
if __name__=='__main__':
    if sys.argv[1]=='--svg-only':Path(sys.argv[3]).write_text(scene_svg(read(sys.argv[2])),encoding='utf-8')
    else:print(json.dumps(produce(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None,'faithful_reconstruction' if len(sys.argv)>3 else 'approved_design'),ensure_ascii=False))
