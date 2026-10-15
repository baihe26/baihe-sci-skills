"""Scene identity/readback/edit checks on owned Illustrator docs using existing bridges.
This is a contract adapter, not another COM server or drawing engine.
"""
from paths import *
from core import writable,source,GateError

JS = r'''
function sameImport(n,id){return n===id||n===id.replace(/_/g,' ');}
function unique(items,id,alias){var found=[];for(var i=0;i<items.length;i++)if(alias?sameImport(items[i].name,id):items[i].name===id)found.push(items[i]);if(found.length!==1)throw Error('IDENTITY_MISSING_OR_AMBIGUOUS '+id+' count='+found.length);return found[0];}
function xy(a){return [Number(a[0]),Number(a[1])];}
function bounds(o){var b=o.geometricBounds;return [Number(b[0]),Number(b[1]),Number(b[2]),Number(b[3])];}
function note(o,id,role,g,sha){var source=null,all=g.groups.concat(g.objects).concat(g.arrow_objects).concat(g.text_objects);for(var i=0;i<all.length;i++)if(all[i].id===id)source=all[i];o.note=JSON.stringify({semantic_id:id,role:role,scene_sha256:sha,source_layer_id:source.layer_id,scientific_refs:source.scientific_refs||[],source_id:source.source_id||null,target_id:source.target_id||null,relation_id:source.relation_id||null,epistemic_status:source.epistemic_status||null,binding:'SceneGraph + scientific_binding sidecar'});}
function members(d,id){return unique(d.groupItems,id,false);}
function openOwned(path){var wanted=new File(path).fsName.toLowerCase();for(var i=0;i<app.documents.length;i++){var p=null;try{p=app.documents[i].fullName.fsName.toLowerCase();}catch(e){}if(p===wanted)throw Error('DOCUMENT_ALREADY_OPEN_SAFE_STOP '+path);}return app.open(new File(path));}
function rgb(hex){var c=new RGBColor();c.red=parseInt(hex.substr(1,2),16);c.green=parseInt(hex.substr(3,2),16);c.blue=parseInt(hex.substr(5,2),16);return c;}
function nativePaths(v){var result=[];function walk(o){if(o.typename==='PathItem'){result.push(o);return;}if(o.typename==='CompoundPathItem'){for(var j=0;j<o.pathItems.length;j++)result.push(o.pathItems[j]);return;}if(o.typename==='GroupItem')for(var j=0;j<o.pageItems.length;j++)walk(o.pageItems[j]);}walk(v);return result;}
function bindScene(d,g,sha){var mapping=[];
 for(var i=0;i<g.groups.length;i++){var item=g.groups[i],v=unique(d.groupItems,item.id,true),old=v.name;v.name=item.id;note(v,item.id,'semantic_group',g,sha);mapping.push({id:item.id,imported_name:old,native_name:v.name,planned_name:item.name});}
 var objs=g.objects.concat(g.arrow_objects);
 for(var i=0;i<objs.length;i++){var item=objs[i],v=unique(d.groupItems,item.id+'_semantic',true),old=v.name;v.name=item.id;note(v,item.id,'semantic_object',g,sha);mapping.push({id:item.id,imported_name:old,native_name:v.name});}
 for(var i=0;i<g.text_objects.length;i++){var item=g.text_objects[i],v=unique(d.textFrames,item.id,true),old=v.name;v.name=item.id;note(v,item.id,'live_text',g,sha);mapping.push({id:item.id,imported_name:old,native_name:v.name});var wrap=unique(d.groupItems,item.id+'_semantic',true);wrap.name=item.id+'__text_container';}
 return mapping;
}
function rgbValue(c){if(!c)return null;var o={type:c.typename};if(c.typename==='RGBColor'){o.r=c.red;o.g=c.green;o.b=c.blue;}else if(c.typename==='GrayColor')o.gray=c.gray;return o;}
function pathState(p){var pts=[];for(var j=0;j<p.pathPoints.length;j++){var q=p.pathPoints[j];pts.push({anchor:xy(q.anchor),left:xy(q.leftDirection),right:xy(q.rightDirection)});}return {name:p.name,bbox:bounds(p),closed:p.closed,filled:p.filled,fill:p.filled?rgbValue(p.fillColor):null,stroked:p.stroked,stroke:p.stroked?rgbValue(p.strokeColor):null,stroke_width:p.strokeWidth,opacity:p.opacity,points:pts};}
function parentNames(o){var a=[],p=o.parent;while(p&&p.typename!=='Document'){if(p.typename==='GroupItem')a.push(p.name);p=p.parent;}return a;}
function siblingOrder(v){var a=v.parent.pageItems;for(var i=0;i<a.length;i++)if(a[i].name===v.name&&a[i].typename===v.typename)return i;throw Error('SIBLING_ORDER_NOT_FOUND '+v.name);}
function state(d,g){var ab=d.artboards[0].artboardRect,items={},all=g.groups.concat(g.objects).concat(g.arrow_objects).concat(g.text_objects);
 for(var i=0;i<all.length;i++){var o=all[i],isText=o.geometry&&o.geometry.kind==='TEXT',v=unique(isText?d.textFrames:d.groupItems,o.id,false),r={id:o.id,name:v.name,type:v.typename,bbox:bounds(v),parents:parentNames(v),note:v.note,z_order:siblingOrder(v)};
  if(isText)r.text={content:v.contents,font:v.textRange.characterAttributes.textFont.name,size:v.textRange.characterAttributes.size};
  else {r.paths=[];var paths=nativePaths(v);for(var k=0;k<paths.length;k++)r.paths.push(pathState(paths[k]));}
  items[o.id]=r;
 }
 return {counts:audit(d),artboard:[Number(ab[0]),Number(ab[1]),Number(ab[2]),Number(ab[3])],objects:items};
}
function vectorPoint(d,g,pt){var b=d.artboards[0].artboardRect,s=g.geometry.coordinate_transform.scale_pt_per_px;return [b[0]+pt[0]*s,b[1]-pt[1]*s];}
function hasAnchor(item,target,tol){var paths=nativePaths(item);for(var i=0;i<paths.length;i++)for(var j=0;j<paths[i].pathPoints.length;j++){var a=paths[i].pathPoints[j].anchor;if(Math.abs(a[0]-target[0])<tol&&Math.abs(a[1]-target[1])<tol)return true;}return false;}
function contractChecks(d,g){var scale=g.geometry.coordinate_transform.scale_pt_per_px,ab=d.artboards[0].artboardRect,checks={width_pt:Math.abs((ab[2]-ab[0])-g.canvas.width*scale)<.05,height_pt:Math.abs((ab[1]-ab[3])-g.canvas.height*scale)<.05,no_raster:d.rasterItems.length===0&&d.placedItems.length===0,live_text_count:d.textFrames.length===g.text_objects.length};
 for(var i=0;i<g.text_objects.length;i++){var o=g.text_objects[i],v=unique(d.textFrames,o.id,false);checks[o.id+'_text']=v.contents===o.text;checks[o.id+'_font_size']=Math.abs(v.textRange.characterAttributes.size-o.font_size*scale)<.03;}
 for(var i=0;i<g.parent_child.length;i++){var o=g.parent_child[i],v;try{v=unique(d.groupItems,o.child_id,false);}catch(e){v=unique(d.textFrames,o.child_id,false);}var ps=parentNames(v),ok=false;for(var j=0;j<ps.length;j++)if(ps[j]===o.parent_id)ok=true;checks[o.parent_id+'__'+o.child_id+'_contained']=ok;}
 for(var i=0;i<g.arrow_objects.length;i++){var o=g.arrow_objects[i],v=members(d,o.id),pts=o.geometry.data.points;checks[o.id+'_source_endpoint']=hasAnchor(v,vectorPoint(d,g,pts[0]),.1);checks[o.id+'_target_endpoint']=hasAnchor(v,vectorPoint(d,g,pts[pts.length-1]),.1);}
 return checks;
}
function translatePoint(q,dx,dy){var a=xy(q.anchor),l=xy(q.leftDirection),r=xy(q.rightDirection);q.anchor=[a[0]+dx,a[1]+dy];q.leftDirection=[l[0]+dx,l[1]+dy];q.rightDirection=[r[0]+dx,r[1]+dy];}
function moveWithRelations(d,g,gid,dx,dy){var v=members(d,gid);v.translate(dx,dy);var ids=[gid],scale=g.geometry.coordinate_transform.scale_pt_per_px;
 for(var i=0;i<g.arrow_objects.length;i++){var r=g.arrow_objects[i],pts=r.geometry.data.points,endpoint=null;if(r.source_id===gid)endpoint=pts[0];if(r.target_id===gid)endpoint=pts[pts.length-1];if(!endpoint)continue;
  var target=vectorPoint(d,g,endpoint),other=vectorPoint(d,g,r.source_id===gid?pts[pts.length-1]:pts[0]),vx=target[0]-other[0],vy=target[1]-other[1],den=vx*vx+vy*vy;if(den<.01)throw Error('COINCIDENT_RELATION_ENDPOINTS');var paths=nativePaths(members(d,r.id));for(var j=0;j<paths.length;j++)for(var k=0;k<paths[j].pathPoints.length;k++){var p=paths[j].pathPoints[k],a=p.anchor,weight=((a[0]-other[0])*vx+(a[1]-other[1])*vy)/den;weight=Math.max(0,Math.min(1,weight));translatePoint(p,dx*weight,dy*weight);}ids.push(r.id);
 }return ids;
}
'''

def existing():
    bridge=load_file('existing_illustrator_bridge',VECTOR/'bridge/illustrator_bridge.py')
    helper=load_file('existing_vector_helpers',VECTOR_HELPERS)
    return bridge.illustrator(),helper

def execute(body,graph,**values):
    app,helper=existing()
    prefix='var graph='+json.dumps(graph,ensure_ascii=False)+';'
    for key,value in values.items():
        prefix+='var '+key+'='+json.dumps(str(value).replace('\\','/'),ensure_ascii=False)+';'
    script=helper.JS_HELPERS+JS+prefix+'''\n(function(){var previous=app.userInteractionLevel;app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;try{\n'''+body+'''\n}catch(e){return out({native_error:String(e),line:e.line,stage:typeof stage==='undefined'?'not_recorded':stage});}finally{app.userInteractionLevel=previous;}})();'''
    result=json.loads(app.DoJavaScript(script))
    if 'native_error' in result:raise GateError(json.dumps(result,ensure_ascii=False))
    return result

def production(svg,scene_path,out):
    graph=read(scene_path);out=writable(out)
    result=execute('''var stage='open';var d=openOwned(input);try{stage='bind';var mapping=bindScene(d,graph,sceneSha);stage='state';var before=state(d,graph);stage='checks';var checks=contractChecks(d,graph),ok=true;for(var k in checks)if(!checks[k])ok=false;stage='export';if(ok)exports(d,stem);stage='done';return out({mapping:mapping,before:before,checks:checks,exported:ok,closed_owned_document:true});}finally{d.close(SaveOptions.DONOTSAVECHANGES);}''',graph,input=svg,sceneSha=sha(scene_path),stem=out/'可编辑图')
    save(out/'原生绑定与尺寸检查.json',result)
    if not all(result['checks'].values()):raise GateError('NATIVE_CONTRACT_FAILED: '+str(out/'原生绑定与尺寸检查.json'))
    return result

def reopen(scene_path,out):
    graph=read(scene_path);out=writable(out);dest=out/'独立客户端重开';dest.mkdir()
    result=execute('''var d=openOwned(input);try{var current=state(d,graph),checks=contractChecks(d,graph);exports(d,stem);return out({snapshot:current,checks:checks,independent_python_client:true,closed_owned_document:true});}finally{d.close(SaveOptions.DONOTSAVECHANGES);}''',graph,input=out/'可编辑图.ai',stem=dest/'重开验证')
    save(dest/'原生重开检查.json',result)
    if not all(result['checks'].values()):raise GateError('NATIVE_REOPEN_CONTRACT_FAILED')
    return result

def edit_probes(scene_path,out):
    graph=read(scene_path);out=writable(out);dest=out/'实际编辑验收';dest.mkdir()
    operations={
        '改字':'''var v=unique(d.textFrames,'AI_text_A',false);v.selected=true;var selection=v.selected;v.contents='Module A*';v.selected=false;var edited={selected:selection,live_text:v.typename,content:v.contents,allowed:['AI_text_A','AI_fig_A']};''',
        '改色':'''var v=members(d,'AI_box_A'),count=0;v.selected=true;var selection=v.selected;for(var k=0;k<v.pathItems.length;k++)if(v.pathItems[k].filled){v.pathItems[k].fillColor=rgb('#88B5D2');count++;}v.selected=false;var edited={selected:selection,recolored_paths:count,allowed:['AI_box_A','AI_fig_A'],expected_rgb:{r:136,g:181,b:210}};''',
        '移动与连线':'''var scale=graph.geometry.coordinate_transform.scale_pt_per_px;var ids=moveWithRelations(d,graph,'AI_fig_A',12*scale,0);var a=members(d,'AI_fig_A');a.selected=true;var selection=a.selected;a.selected=false;var edited={selected:selection,delta_pt:[12*scale,0],incident_ids:ids,allowed:['AI_fig_A','AI_box_A','AI_text_A','AI_R1','AI_R2']};''',
        '局部关系':'''var v=members(d,'AI_R1'),n=0,scale=graph.geometry.coordinate_transform.scale_pt_per_px;for(var j=0;j<v.pathItems.length;j++){var p=v.pathItems[j];if(p.pathPoints.length===2){var a=xy(p.pathPoints[0].anchor),b=xy(p.pathPoints[1].anchor);p.setEntirePath([a,[(a[0]+b[0])/2,a[1]+8*scale],b]);n++;break;}}var edited={modified_native_paths:n,scientific_source_id:'AI_fig_A',scientific_target_id:'AI_fig_B',relation_id:'R1',allowed:['AI_R1'],endpoints_preserved:true};'''
    }
    results=[]
    for name,operation in operations.items():
        folder=dest/name;folder.mkdir()
        body='''var d=openOwned(input);try{var before=state(d,graph);'''+operation+'''var after=state(d,graph);exports(d,stem);}finally{d.close(SaveOptions.DONOTSAVECHANGES);}var q=openOwned(saved);try{var reopened=state(q,graph);exports(q,reopenStem);return out({operation:edited,before:before,after:after,reopened:reopened});}finally{q.close(SaveOptions.DONOTSAVECHANGES);}'''
        result=execute(body,graph,input=out/'可编辑图.ai',stem=folder/'编辑测试_非交付',saved=folder/'编辑测试_非交付.ai',reopenStem=folder/'重开验证')
        save(folder/'原生编辑读回.json',result);results.append(dict(name=name,folder=str(folder)))
    save(dest/'编辑案例索引.json',dict(cases=results,scope='Synthetic simple scene only; edit probes are not scientific results'))
    return results

if __name__=='__main__':
    mode,scene,out=sys.argv[1:4]
    if mode=='reopen':print(json.dumps(reopen(scene,out),ensure_ascii=False))
    elif mode=='edit':print(json.dumps(edit_probes(scene,out),ensure_ascii=False))
    else:raise ValueError(mode)
