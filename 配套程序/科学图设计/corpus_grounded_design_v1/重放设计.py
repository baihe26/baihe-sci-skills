"""小型确定性合同/预览重放：仅图元序列化，不作科学解释、候选选择或生产执行。"""
from pathlib import Path
from handoff_metadata import build_local_qa_gate
import json, math, html, copy, hashlib, base64, re
import fitz
from 整理研究证据 import ROOT,REPO,read,dump,write,sha

def xyxy(b):x,y,w,h=b;return [x,y,x+w,y+h]
def union(boxes):return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
def arrow_paths(points,encoding):
    tail,end=points[-2:];dx=end[0]-tail[0];dy=end[1]-tail[1];length=math.hypot(dx,dy) or 1;ux,uy=dx/length,dy/length
    if encoding=='inhibition_bar':return [[end[0]-uy*9,end[1]+ux*9],[end[0]+uy*9,end[1]-ux*9]]
    if encoding in ['solid_arrow','dashed_arrow']:return [[end[0]-ux*11-uy*5,end[1]-uy*11+ux*5],end,[end[0]-ux*11+uy*5,end[1]-uy*11-ux*5]]
    return []
def dashed_lines(points,color,width=2,pattern=(6,5)):
    # 预览显式小线段，避免轻量 SVG->PNG 后端忽略 dash 属性；并非新增语义边。
    out=[];phase=0.0;period=sum(pattern)
    for a,b in zip(points,points[1:]):
        length=math.dist(a,b)
        if not length:continue
        at=0.0
        while at<length-1e-8:
            mod=phase%period;on=mod<pattern[0];step=min(length-at,(pattern[0]-mod) if on else (period-mod))
            if on:
                p=[a[i]+(b[i]-a[i])*at/length for i in range(2)];q=[a[i]+(b[i]-a[i])*(at+step)/length for i in range(2)]
                out.append(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{color}" stroke-width="{width}"/>')
            at+=step;phase+=step
    return ''.join(out)
def flattened_outline(kind,a):
    if kind=='POLYLINE':return a['points']
    if kind=='RECT':x,y,w,h=a['x'],a['y'],a['width'],a['height'];return [[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]]
    if kind=='ELLIPSE':return [[a['cx']+a['rx']*math.cos(i*math.tau/120),a['cy']+a['ry']*math.sin(i*math.tau/120)] for i in range(121)]
    if kind=='PATH':
        tokens=re.findall(r'[MQLZ]|-?\d+(?:\.\d+)?',a['d']);i=0;points=[]
        while i<len(tokens):
            cmd=tokens[i];i+=1
            if cmd in ['M','L']:p=[float(tokens[i]),float(tokens[i+1])];i+=2;points.append(p)
            elif cmd=='Q':
                c=[float(tokens[i]),float(tokens[i+1])];end=[float(tokens[i+2]),float(tokens[i+3])];i+=4;start=points[-1]
                for n in range(1,31):
                    t=n/30;points.append([(1-t)**2*start[j]+2*(1-t)*t*c[j]+t*t*end[j] for j in range(2)])
            elif cmd=='Z':points.append(points[0])
            else:raise ValueError('dashed path unsupported command: '+cmd)
        return points
    raise ValueError(kind)
def element_svg(e):
    a=e['data'];kind=e['kind'];esc=lambda x:html.escape(str(x),quote=True)
    style=f'fill="{esc(e["fill"])}" stroke="{esc(e["stroke"])}" stroke-width="{e["stroke_width"]}"'
    if e.get('dash'):style+=f' stroke-dasharray="{esc(e["dash"])}"'
    name=f'id="{esc(e["id"])}" data-owner="{esc(e.get("owner") or "annotation")}"'
    if e.get('dash') and kind!='TEXT':
        solid=copy.deepcopy(e);solid['dash']=None;solid['stroke_width']=0
        return f'<g {name}>'+element_svg(dict(solid,id=e['id']+'_fill'))+dashed_lines(flattened_outline(kind,a),e['stroke'],e['stroke_width'])+'</g>'
    if kind=='TEXT':return f'<text {name} x="{a["x"]}" y="{a["y"]}" fill="{esc(e["fill"])}" font-family="Arial, sans-serif" font-size="{a["font_size"]}" text-anchor="{a["anchor"]}">{esc(a["text"])}</text>'
    if kind=='RECT':return f'<rect {name} x="{a["x"]}" y="{a["y"]}" width="{a["width"]}" height="{a["height"]}" {style}/>'
    if kind=='ELLIPSE':return f'<ellipse {name} cx="{a["cx"]}" cy="{a["cy"]}" rx="{a["rx"]}" ry="{a["ry"]}" {style}/>'
    if kind=='PATH':return f'<path {name} d="{esc(a["d"])}" {style}/>'
    if kind=='POLYLINE':return f'<polyline {name} points="'+ ' '.join(f'{p[0]},{p[1]}' for p in a['points'])+f'" {style}/>'
    raise ValueError(kind)
def svg(plan,spec):
    w,h=plan['canvas'];out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img"><title>{html.escape(spec["central_message"])}</title><rect width="100%" height="100%" fill="white"/>']
    clips={c['owner']:c for c in plan.get('clips',[])}
    for owner,c in clips.items():
        a=c['rect'];out.append(f'<defs><clipPath id="clip_{html.escape(owner)}"><rect x="{a[0]}" y="{a[1]}" width="{a[2]}" height="{a[3]}"/></clipPath></defs>')
    def rendered(e):
        s=element_svg(e)
        return '<g clip-path="url(#clip_'+html.escape(e['owner'])+')">'+s+'</g>' if e.get('owner') in clips else s
    for e in plan['elements']:
        if e['kind']!='TEXT':out.append(rendered(e))
    for r in plan['relations']:
        points=r['points'];s=' '.join(f'{p[0]},{p[1]}' for p in points);dashed=r['epistemic_status'] in ['UNKNOWN','HYPOTHESIZED','PROPOSED','RESEARCH_GOAL'];color='#ab8050' if dashed else '#526873';dash=' stroke-dasharray="6 5"' if dashed else ''
        out.append(f'<g id="{r["id"]}" data-relation="{r["relation_id"]}">'+(dashed_lines(points,color,2.2) if dashed else f'<polyline points="{s}" fill="none" stroke="{color}" stroke-width="2.2"/>'))
        arrow=arrow_paths(points,r['encoding'])
        if arrow:out.append('<polyline points="'+' '.join(f'{p[0]},{p[1]}' for p in arrow)+f'" fill="none" stroke="{color}" stroke-width="2.2"/>')
        out.append('</g>')
    out.extend(rendered(e) for e in plan['elements'] if e['kind']=='TEXT');out.append('</svg>');return '\n'.join(out)
def raster(svg_text,path):
    # SVG 新创作科学设计的标准渲染；不编辑论文图片，不调用图像模型。
    with fitz.open(stream=svg_text.encode(),filetype='svg') as doc:
        pdf=doc.convert_to_pdf()
    with fitz.open(stream=pdf,filetype='pdf') as doc:
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.25,1.25),alpha=False);pix.save(path)
def make_scene(spec,plan,folder):
    layers=[dict(id='L_context',name='Context and owned placeholder',z_order=0),dict(id='L_science',name='Scientific objects',z_order=1),dict(id='L_relations',name='Semantic relations',z_order=2),dict(id='L_text',name='Live labels',z_order=3)]
    graph=dict(schema_version='1.0',canvas=dict(width=plan['canvas'][0],height=plan['canvas'][1],unit='px',origin='TOP_LEFT'),layers=layers,objects=[],groups=[],geometry={},bbox=[0,0,*plan['canvas']],z_order=[],parent_child=[],clipping=[],style_tokens={},text_objects=[],arrow_objects=[],asset_refs=[],render_method='NATIVE_VECTOR',editability_level='FULL_NATIVE')
    owners={i['id']:i for i in plan['instances']};els=copy.deepcopy(plan['elements']); asset_owner='fig_E_VESSEL_bulk'
    # D02 的复杂类对象：交接为一个原创矢量 placeholder asset，保持整体移动/替换计划。
    if asset_owner in owners:
        own=[e for e in els if e['owner']==asset_owner];w,h=plan['canvas'];asset_plan=dict(canvas=[w,h],elements=own,relations=[])
        own_svg=svg(asset_plan,spec);asset=folder/'design_assets/原创血管占位.svg';write(asset,own_svg)
        graph['asset_refs'].append(dict(asset_id='asset_vessel',local_path=str(asset),sha256=sha(asset),rights_basis='OWN_ORIGINAL_DESIGN_PLACEHOLDER; no published artwork reused',editability_level='ASSET_EDITABLE',render_method='REUSABLE_ASSET',placeholder=True))
        els=[e for e in els if e['owner']!=asset_owner]
        els.insert(0,dict(id='owned_vessel_asset',owner=asset_owner,kind='ASSET_PLACEMENT',data=dict(asset_id='asset_vessel',original_viewbox=[0,0,w,h],native_preview_elements=own),bbox=owners[asset_owner]['bbox'],stroke='#687c87',fill='none',stroke_width=0,scientific_refs=['E_VESSEL','E_WALL','E_INTIMA','E_ADVENTITIA'],role='object'))
        graph['render_method']='REUSABLE_ASSET';graph['editability_level']='GROUP_EDITABLE'
    n=0
    for e in sorted(els,key=lambda x:x['kind']=='TEXT'):
        token='style_'+e['id'];graph['style_tokens'][token]=dict(fill=None if e['fill']=='none' else e['fill'],stroke=None if e['stroke_width']==0 else e['stroke'],stroke_width=e['stroke_width'],opacity=1)
        owner=e['owner'];geometry=dict(kind=e['kind'],data=copy.deepcopy(e['data']));geometry['data']['dash']=e.get('dash')
        item=dict(id='AI_'+e['id'],layer_id='L_text' if e['kind']=='TEXT' else 'L_context' if e['kind']=='ASSET_PLACEMENT' else 'L_science',group_id='AI_'+owner if owner else None,bbox=xyxy(e['bbox']),z_order=n,style_token=token,geometry=geometry,render_method='REUSABLE_ASSET' if e['kind']=='ASSET_PLACEMENT' else 'PROCEDURAL_VECTOR' if owners.get(owner,{}).get('shape') in ['fibers','cell','nucleus'] else 'NATIVE_VECTOR',editability_level='ASSET_EDITABLE' if e['kind']=='ASSET_PLACEMENT' else 'FULL_NATIVE',scientific_refs=e['scientific_refs']);n+=1
        if e['kind']=='TEXT':
            item.update(text=e['data']['text'],font_family='Arial',font_size=e['data']['font_size'],live_text_required=True);graph['text_objects'].append(item)
        else:graph['objects'].append(item)
    for r in plan['relations']:
        token='style_'+r['id'];dashed=r['epistemic_status'] in ['UNKNOWN','PROPOSED','HYPOTHESIZED','RESEARCH_GOAL'];graph['style_tokens'][token]=dict(fill=None,stroke='#ab8050' if dashed else '#526873',stroke_width=2.2,opacity=1)
        pts=r['points'];box=[min(x[0] for x in pts),min(x[1] for x in pts),max(x[0] for x in pts),max(x[1] for x in pts)]
        graph['arrow_objects'].append(dict(id='AI_'+r['id'],layer_id='L_relations',group_id=None,bbox=box,z_order=n,style_token=token,geometry=dict(kind='POLYLINE',data=dict(points=pts,encoding=r['encoding'],dash='6 5' if dashed else None)),render_method='NATIVE_VECTOR',editability_level='FULL_NATIVE',scientific_refs=[r['relation_id'],*r['claim_ids']],source_id='AI_'+r['source'],target_id='AI_'+r['target'],relation_id=r['relation_id'],arrow_semantics=r['predicate'],epistemic_status=r['epistemic_status'],negated=r['negated']));n+=1
    allitems=graph['objects']+graph['text_objects']+graph['arrow_objects']
    for owner,i in owners.items():
        b=[o['bbox'] for o in allitems if o['group_id']=='AI_'+owner]
        if not b:b=[xyxy(i['bbox'])]
        graph['groups'].append(dict(id='AI_'+owner,layer_id='L_science',name='AI_'+i['entity_id']+'__'+owner,bbox=union(b),z_order=0))
        for o in allitems:
            if o['group_id']=='AI_'+owner:graph['parent_child'].append(dict(parent_id='AI_'+owner,child_id=o['id']))
    for p in plan['parent_semantics']:graph['parent_child'].append(dict(parent_id='AI_'+p['parent_id'],child_id='AI_'+p['child_id']))
    by_group={g['id']:g for g in graph['groups']}
    # 可移动父组的 bbox 必须容纳其递归成员，而不是只用标题文本 footprint。
    for _ in range(len(by_group)):
        for link in graph['parent_child']:
            if link['parent_id'] in by_group and link['child_id'] in by_group:
                p,c=by_group[link['parent_id']],by_group[link['child_id']];p['bbox']=union([p['bbox'],c['bbox']])
    if asset_owner in owners:
        clip=dict(id='AI_clip_surface_field',layer_id='L_context',group_id=None,bbox=[618,214,893,287],z_order=0,style_token='clip',geometry=dict(kind='RECT',data=dict(x=618,y=214,width=275,height=73,is_clip=True)),render_method='NATIVE_VECTOR',editability_level='FULL_NATIVE',scientific_refs=['E_HYDROGEL','E_ADVENTITIAL_SURFACE'])
        graph['style_tokens']['clip']=dict(fill=None,stroke=None,stroke_width=0,opacity=1);graph['objects'].append(clip);graph['clipping']=[dict(clip_path_id=clip['id'],target_group_id='AI_fig_E_HYDROGEL_local')]
    # construction z-order puts all text above objects and relations; group ids are explicit containers.
    ordered=graph['objects']+graph['arrow_objects']+graph['text_objects']
    for j,o in enumerate(ordered):o['z_order']=j
    graph['z_order']=[g['id'] for g in graph['groups']]+[o['id'] for o in ordered]
    graph['geometry']['coordinate_transform']=dict(from_unit='px',to_illustrator_unit='pt',scale_pt_per_px=183/1200*72/25.4,y_axis='TOP_LEFT to Illustrator artboard coordinates; adapter must test')
    dump(folder/'IllustratorSceneGraph.json',graph)
    mapping=[]
    for i in plan['instances']:
        mapping.append(dict(content_ir_entity_id=i['entity_id'],figure_spec_id=i['id'],scene_group_id='AI_'+i['id'],planned_illustrator_group_name='AI_'+i['entity_id']+'__'+i['id'],scene_children=[o['id'] for o in ordered if o['group_id']=='AI_'+i['id']]))
    primitive_map=[dict(content_ir_ref_ids=e['scientific_refs'],figure_construction_id=e['id'],scene_object_id='AI_'+e['id'],planned_illustrator_object_name='AI_'+e['id']) for e in plan['elements'] if e['scientific_refs'] and e['owner']!=asset_owner]
    dump(folder/'HANDOFF_EXECUTION_CONTRACT.json',dict(version='1.0',execution_status='PREPARED_NOT_EXECUTED',figure_spec_sha256=sha(folder/'FigureSpec.json'),construction_sha256=sha(folder/'ConstructionPlan.json'),scenegraph_sha256=sha(folder/'IllustratorSceneGraph.json'),regions=spec['layout_zones'],semantic_id_map=mapping,relation_id_map=[dict(content_ir_relation_id=r['relation_id'],figure_spec_relation_id=r['id'],scene_relation_id='AI_'+r['id'],planned_illustrator_name='AI_'+r['id']) for r in plan['relations']],construction_order=['validate scientific_binding original statuses and source spans','convert XYWH to XYXY; apply unit and y transform','create semantic layer/group names and logical parent-child','create native outlines and owned placeholder placement','apply explicit clip pairs only','create relation objects with endpoint id references and original epistemic state','create live text after geometry; preserve font identities','run local QA then await human acceptance'],local_qa_gate=build_local_qa_gate(spec),native_editability_tests_status='NOT_EXECUTED',production_engine_modified=False,scientific_status_sidecar_required=True))
    contract=read(folder/'HANDOFF_EXECUTION_CONTRACT.json');contract['scientific_primitive_id_map']=primitive_map;dump(folder/'HANDOFF_EXECUTION_CONTRACT.json',contract)
    # SceneGraph preview is built from SceneGraph objects, not a copied candidate PNG.
    scene_plan=dict(canvas=plan['canvas'],elements=[],relations=[],clips=[])
    for c in graph['clipping']:
        o=next(o for o in graph['objects'] if o['id']==c['clip_path_id']);a=o['geometry']['data'];scene_plan['clips'].append(dict(owner=c['target_group_id'],rect=[a['x'],a['y'],a['width'],a['height']]))
    for o in graph['objects']+graph['text_objects']:
        if o['geometry']['data'].get('is_clip'):continue
        if o['geometry']['kind']=='ASSET_PLACEMENT':scene_plan['elements'].extend(o['geometry']['data']['native_preview_elements']);continue
        s=graph['style_tokens'][o['style_token']];b=o['bbox'];scene_plan['elements'].append(dict(id=o['id'],owner=o['group_id'],kind=o['geometry']['kind'],data=o['geometry']['data'],bbox=[b[0],b[1],b[2]-b[0],b[3]-b[1]],fill=s['fill'] or 'none',stroke=s['stroke'] or 'none',stroke_width=s['stroke_width'],dash=o['geometry']['data'].get('dash')))
    for o in graph['arrow_objects']:scene_plan['relations'].append(dict(id=o['id'],relation_id=o['relation_id'],points=o['geometry']['data']['points'],encoding=o['geometry']['data']['encoding'],epistemic_status=o['epistemic_status']))
    scene_svg=svg(scene_plan,spec);write(folder/'SceneGraph_preview.svg',scene_svg);raster(scene_svg,folder/'SceneGraph_preview.png')
    return graph
def render_all():
    count=0
    for folder in sorted((ROOT/'设计结果').glob('*/*')):
        if not (folder/'FigureSpec.json').exists():continue
        spec=read(folder/'FigureSpec.json');plan=read(folder/'ConstructionPlan.json')
        text=svg(plan,spec);write(folder/'layout_preview.svg',text);raster(text,folder/'layout_preview.png');count+=1
        if folder.name=='PRIMARY' and folder.parent.name in ['D02','V01','V04']:make_scene(spec,plan,folder)
    print('Previews:',count,'SceneGraph representatives: D02 V01 V04')
if __name__=='__main__':render_all()
