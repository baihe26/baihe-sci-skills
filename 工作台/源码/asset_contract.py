"""Retain original image bytes and explicit rectangular crop provenance."""
import math
from paths import sha
from core import GateError
from scientific_gate import indexed, resolve_file


def box_valid(box, width, height, integer=False):
    return len(box)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) and (not integer or type(v) is int) for v in box) and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height


def union_area(boxes):
    if not boxes: return 0
    xs=sorted({v for b in boxes for v in (b[0],b[2])}); area=0
    for left,right in zip(xs,xs[1:]):
        ranges=sorted((b[1],b[3]) for b in boxes if b[0] < right and b[2] > left)
        total=0;end=None
        for top,bottom in ranges:
            if end is None or top > end: total += bottom-top;end=bottom
            elif bottom > end: total += bottom-end;end=bottom
        area += (right-left)*total
    return area


def check_assets(contract, base, graph):
    from PIL import Image
    records=indexed(contract.get('assets', []))
    native_ids={o['id'] for key in ('objects','text_objects','arrow_objects','groups') for o in graph[key]}
    groups={g['id'] for g in graph['groups']}
    if len(records)>200: raise GateError('ASSET_CONTRACT_TOO_LARGE')
    result=[]
    for identity,row in records.items():
        if identity in native_ids: raise GateError('ASSET_NATIVE_ID_COLLISION')
        if row.get('content_kind') not in ('scientific_image','photograph','texture') or row.get('editability')!='MOVE_SCALE_REPLACE': raise GateError('ASSET_NOT_NATIVE_GEOMETRY')
        if not row.get('reason') or not row.get('source_ref'): raise GateError('ASSET_REASON_AND_SOURCE_REQUIRED')
        path=resolve_file(base,row['source']['path'])
        if not path.is_file() or sha(path)!=row['source']['sha256']: raise GateError('ASSET_SOURCE_HASH_CONFLICT: '+identity)
        with Image.open(path) as image:
            width,height=image.size;image_format=image.format
            if image.format not in ('PNG','JPEG') or getattr(image,'n_frames',1)!=1: raise GateError('ASSET_FORMAT_USE_VERIFIED_LEGACY_ROUTE')
            if image.getexif().get(274,1)!=1: raise GateError('ASSET_ORIENTATION_REQUIRES_EXPLICIT_REVIEW')
        if [width,height]!=row['source']['size_px']: raise GateError('ASSET_SOURCE_DIMENSIONS_CONFLICT')
        region=row.get('source_box_px',[0,0,width,height]); placement=row['bbox']
        if not box_valid(region,width,height,integer=True) or not box_valid(placement,graph['canvas']['width'],graph['canvas']['height']): raise GateError('ASSET_CROP_OR_PLACEMENT_INVALID')
        aspect=(region[2]-region[0])/(region[3]-region[1]);actual=(placement[2]-placement[0])/(placement[3]-placement[1])
        if abs(actual/aspect-1)>.001: raise GateError('SCIENTIFIC_IMAGE_STRETCH_FORBIDDEN')
        if row.get('group_id') is not None and row['group_id'] not in groups: raise GateError('ASSET_PARENT_UNRESOLVED')
        result.append(dict(row,source_path=str(path),source_box_px=region,source_sha256=sha(path),source_format=image_format,
                           crop_box_normalized=[region[0]/width,region[1]/height,region[2]/width,region[3]/height]))
    coverage=[]
    for path in sorted({row['source_path'] for row in result}):
        subset=[r for r in result if r['source_path']==path];w,h=subset[0]['source']['size_px']
        coverage.append(dict(source_sha256=subset[0]['source_sha256'],union_coverage=union_area([r['source_box_px'] for r in subset])/(w*h)))
    return dict(status='PASS',assets=result,source_union_coverage=coverage,
                pixels='ORIGINAL_FILE_BYTES_MUST_BE_EMBEDDED_WITH_NATIVE_CROP',scientific_review='PENDING')


def check_reconstruction(contract, base, graph, assets):
    source=contract['source'];path=resolve_file(base,source['path'])
    if not path.is_file() or sha(path)!=source['sha256']: raise GateError('RECONSTRUCTION_SOURCE_HASH_CONFLICT')
    from PIL import Image
    with Image.open(path) as image:
        if list(image.size)!=source['size_px']: raise GateError('RECONSTRUCTION_SOURCE_SIZE_CONFLICT')
    width,height=source['size_px'];elements=indexed(contract['elements'])
    if not set(contract['required_ids']) <= set(elements): raise GateError('RECONSTRUCTION_ELEMENT_MISSING')
    native={o['id']:o for k in ('objects','text_objects','arrow_objects','groups') for o in graph[k]}
    raster={row['id']:row for row in assets['assets']};uncertain=[]
    for identity,row in elements.items():
        regions=row.get('source_boxes_px',[row.get('source_box_px',[])])
        if not regions or len(regions)>200 or any(not box_valid(region,width,height) for region in regions): raise GateError('RECONSTRUCTION_REGION_INVALID')
        outputs=row.get('output_ids',[])
        unresolved_omission=row.get('uncertain') and row.get('disposition')=='omitted_pending_review'
        if (not outputs and not unresolved_omission) or not set(outputs)<=set(native)|set(raster): raise GateError('RECONSTRUCTION_OUTPUT_UNRESOLVED')
        if row.get('native_required') and not set(outputs)<=set(native): raise GateError('RECONSTRUCTION_FAKE_NATIVE')
        if row.get('uncertain'):
            if row.get('resolved_text') is not None or row.get('review_status')=='APPROVED': raise GateError('UNCERTAIN_TEXT_GUESSED_OR_APPROVED')
            uncertain.append(identity)
        elif 'observed_text' in row:
            texts=[native[key]['geometry']['data']['text'] for key in outputs if key in native and native[key].get('geometry',{}).get('kind')=='TEXT']
            if texts != [row['observed_text']]: raise GateError('RECONSTRUCTION_TEXT_CONFLICT')
        if row.get('native_required'):
            crops=[]
            for asset in raster.values():
                if asset['source_sha256']!=source['sha256']:continue
                for region in regions:
                    b=asset['source_box_px'];intersection=[max(region[0],b[0]),max(region[1],b[1]),min(region[2],b[2]),min(region[3],b[3])]
                    if intersection[2]>intersection[0] and intersection[3]>intersection[1]:crops.append(intersection)
            fraction=union_area(crops)/union_area(regions)
            if fraction>.05: raise GateError('RASTER_COVERS_REQUIRED_NATIVE_REGION: '+identity)
            parents={v['child_id']:v['parent_id'] for v in graph['parent_child']}
            primitives=[o for k in ('objects','text_objects','arrow_objects') for o in graph[k]]
            def root(key):
                while key in parents:key=parents[key]
                return key
            for output_id in outputs:
                if output_id not in native or 'geometry' not in native[output_id]:continue
                obj=native[output_id];root_id=root(output_id)
                root_z=min(p['z_order'] for p in primitives if root(p['id'])==root_id)
                data=obj['geometry']['data']
                if obj['geometry']['kind']=='POLYLINE':
                    target_regions=[[min(a[0],b[0])-2,min(a[1],b[1])-2,max(a[0],b[0])+2,max(a[1],b[1])+2] for a,b in zip(data['points'],data['points'][1:])]
                else:target_regions=[obj['bbox']]
                overlaps=[]
                for asset in raster.values():
                    if asset.get('group_id') is not None or asset.get('z_order',0)<=root_z:continue
                    for target_region in target_regions:
                        b=asset['bbox'];v=[max(target_region[0],b[0]),max(target_region[1],b[1]),min(target_region[2],b[2]),min(target_region[3],b[3])]
                        if v[2]>v[0] and v[3]>v[1]:overlaps.append(v)
                if union_area(overlaps)>.05*union_area(target_regions):raise GateError('RASTER_OCCLUDES_REQUIRED_OUTPUT: '+output_id)
    return dict(status='NEEDS_REVIEW' if uncertain else 'PASS',accounted=len(elements),uncertain_ids=uncertain,
                unresolved_elements=[elements[key] for key in uncertain],source_sha256=source['sha256'],
                scope='Declared source regions; not automatic image understanding or hidden-content recovery')
