"""Host-authored design artifacts -> existing frozen compiler validation and replay."""
from paths import *
from core import writable,source,GateError
import copy, shutil
from scientific_gate import validate_design,validate_scene
def replay():
    sys.path.insert(0,str(DESIGN/'corpus_grounded_design_v1'))
    return load_file('workbench_frozen_replay',DESIGN/'corpus_grounded_design_v1/重放设计.py')
def compile_design(spec_path,plan_path,binding_path,out):
    import jsonschema
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    spec,plan,binding=map(read,[spec_path,plan_path,binding_path])
    jsonschema.validate(spec,read(HANDOFF/'schemas/figure_spec.schema.json'))
    consistency=validate_design(spec,plan,binding,Path(spec_path).parent,Path(binding_path).parent)
    if not binding or not binding.get('claims'):raise GateError('SCIENTIFIC_BINDING_REQUIRED')
    entities={e['id'] for e in spec['entities']};claims={c['id'] for c in spec['scientific_claims']}
    for c in spec['scientific_claims']:
        sp=c['source_span']
        if spec['metadata']['input_text'][sp['start']:sp['end']]!=sp['quote']:raise GateError('SOURCE_SPAN_MISMATCH')
    for r in spec['relationships']:
        if r['source'] not in entities or r['target'] not in entities or r['claim_id'] not in claims:raise GateError('RELATION_ID_UNRESOLVED')
        if r['certainty'] in ('HYPOTHESIZED','INFERRED') and r['visual_encoding'] in ('solid_arrow','inhibition_bar'):raise GateError('HYPOTHESIS_UPGRADED')
    if {r['id'] for r in plan['relations']}!={r['id'] for r in spec['relationships']}:raise GateError('PLAN_RELATIONS_DIFFER')
    # Carry relative source files into this new output, without rewriting source contracts.
    source_copies={}
    for base,ref in [(Path(spec_path).parent,v['path']) for v in spec['metadata']['sources']]+[(Path(binding_path).parent,binding['source_file']['path'])]:
        relative=Path(ref)
        if relative.is_absolute():continue
        if '..' in relative.parts:raise GateError('RELATIVE_SOURCE_PARENT_TRAVERSAL_USE_ABSOLUTE_REFERENCE')
        if str(relative) in ('FigureSpec.json','ConstructionPlan.json','scientific_binding.json'):raise GateError('SOURCE_CONTRACT_NAME_COLLISION')
        src=(base/relative).resolve()
        if relative in source_copies and sha(src)!=sha(source_copies[relative]):raise GateError('RELATIVE_SOURCE_COLLISION')
        source_copies[relative]=src
    out.mkdir(parents=True)
    for relative,src in source_copies.items():
        (out/relative).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,out/relative)
    for p,n in [(spec_path,'FigureSpec.json'),(plan_path,'ConstructionPlan.json'),(binding_path,'scientific_binding.json')]:shutil.copy2(p,out/n)
    replayer=replay();preview=replayer.svg(plan,spec)
    (out/'设计预览.svg').write_text(preview,encoding='utf-8');replayer.raster(preview,out/'设计预览.png')
    graph=replayer.make_scene(spec,plan,out)
    # Frozen helper assumes 1200px. New tasks may use other canvas widths.
    # Preserve its output and bind a documented, reversible administrative unit correction.
    scale=spec['style']['canvas_width_mm']/graph['canvas']['width']*72/25.4
    old_scale=graph['geometry']['coordinate_transform']['scale_pt_per_px']
    if abs(scale-old_scale)>1e-10:
        archive=out/'原始编译器输出';archive.mkdir()
        for name in ['IllustratorSceneGraph.json','HANDOFF_EXECUTION_CONTRACT.json']:(archive/name).write_bytes((out/name).read_bytes())
        graph['geometry']['coordinate_transform']['scale_pt_per_px']=scale
        (out/'IllustratorSceneGraph.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
        execution=read(out/'HANDOFF_EXECUTION_CONTRACT.json');execution['scenegraph_sha256']=sha(out/'IllustratorSceneGraph.json')
        (out/'HANDOFF_EXECUTION_CONTRACT.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2),encoding='utf-8')
        save(out/'物理尺寸兼容映射.json',dict(parent=source(archive/'IllustratorSceneGraph.json'),original_scale=old_scale,corrected_scale=scale,reason='新画布宽度不是冻结helper的1200px；从FigureSpec物理宽度推导，不改科学内容或几何',frozen_source_modified=False))
    jsonschema.validate(graph,read(HANDOFF/'schemas/illustrator_scene_graph.schema.json'))
    scene_consistency=validate_scene(spec,plan,graph)
    save(out/'跨合同一致性检查.json',dict(design=consistency,scene=scene_consistency))
    from processing_ledger import from_scene
    save(out/'元素处理清单.json',from_scene(graph))
    save(out/'设计交接记录.json',dict(status='DESIGN_HANDOFF_READY_PENDING_REVIEW',host_reasoning='HOST_AUTHORED_ARTIFACTS_NOT_UNATTENDED_MODEL',sources=[source(spec_path),source(plan_path),source(binding_path)],
       scientific_review='PENDING',author_acceptance='PENDING',native_production='NOT_EXECUTED',paid_services=False,designer_freeze_unchanged=True))
    return dict(output=str(out),scenegraph=str(out/'IllustratorSceneGraph.json'),production_started=False)
if __name__=='__main__':print(json.dumps(compile_design(*sys.argv[1:]),ensure_ascii=False))
