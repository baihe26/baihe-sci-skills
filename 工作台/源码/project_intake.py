"""Declared-file intake and physical panel candidates; no directory scan or image alteration."""
from paths import Path, read, save, sha
from core import GateError, source, writable, readable
from scientific_gate import indexed, resolve_file
from asset_contract import box_valid
import math, html


def unknown_fields(value,prefix=''):
    if isinstance(value,dict):
        if not value:return [prefix] if prefix else []
        return [p for k,v in value.items() for p in unknown_fields(v,(prefix+'.' if prefix else '')+str(k))]
    if isinstance(value,list) and value:
        return [p for i,v in enumerate(value) for p in unknown_fields(v,prefix+'['+str(i)+']')]
    unknown=value is None or value==[] or (isinstance(value,str) and value.strip().upper() in ('','UNKNOWN','NOT_RECORDED','HOLD','CONFLICT','待核对','待确认','未知'))
    return [prefix] if unknown else []


def inspect_project(manifest_path):
    manifest_path=Path(manifest_path).resolve(); bound=source(manifest_path); m=read(manifest_path)
    if m.get('schema_version')!='project-intake-0.1' or not m.get('project_id'):
        raise GateError('PROJECT_INTAKE_IDENTITY_REQUIRED')
    rows=indexed(m['sources']); sources=[]; pending=[]
    for identity,row in rows.items():
        if row.get('kind') not in ('numerical_data','data_plot','scientific_image','schematic','reference'):
            raise GateError('PROJECT_SOURCE_KIND_REQUIRED')
        ref=source(resolve_file(manifest_path.parent,row['path']),row.get('sha256'))
        state=row.get('review_status','UNKNOWN')
        if state not in ('CONFIRMED','HOLD','UNKNOWN','CONFLICT'):raise GateError('PROJECT_REVIEW_STATUS_INVALID')
        facts=row.get('scientific_metadata',{})
        if not isinstance(facts,dict):raise GateError('SCIENTIFIC_METADATA_MUST_BE_OBJECT')
        missing=unknown_fields(facts)
        if row['kind']=='numerical_data':
            missing=list(dict.fromkeys([*missing,*[k for k in ('experimental_unit','statistical_n','uncertainty','units','denominator','design') if k not in facts]]))
        reason=row.get('review_reason') or ('科学字段仍有未知/待核对项' if missing else '输入状态尚未确认；原因未记录' if state!='CONFIRMED' else None)
        if missing or state!='CONFIRMED':pending.append(dict(source_id=identity,review_status=state,missing_fields=missing,reason=reason))
        sources.append(dict(id=identity,kind=row['kind'],source=ref,review_status=state,missing_fields=missing,
            review_reason=reason,scientific_metadata=facts,facts='HOST_DECLARED_NOT_INDEPENDENTLY_VERIFIED'))
    panels=indexed(m.get('panels',[]))
    for panel in panels.values():
        if panel.get('source_id') not in rows:raise GateError('PANEL_SOURCE_UNRESOLVED')
    uses=indexed(m.get('figure_uses',[]),'source_figure_id')
    for row in uses.values():
        if row.get('placements') and (not isinstance(row['placements'],list) or any(not isinstance(v,str) or not v.strip() for v in row['placements'])):
            raise GateError('FIGURE_PLACEMENTS_MUST_BE_NONEMPTY_LOCATORS')
        if row.get('unused_reason') and not isinstance(row['unused_reason'],str):raise GateError('FIGURE_UNUSED_REASON_MUST_BE_TEXT')
        if bool(row.get('placements'))==bool(row.get('unused_reason')):
            raise GateError('FIGURE_USE_POSITION_OR_UNUSED_REASON_REQUIRED')
    required=m.get('required_figure_ids',[])
    if not isinstance(required,list) or any(not isinstance(v,str) or not v for v in required):raise GateError('REQUIRED_FIGURE_IDS_MUST_BE_LIST')
    uncovered=sorted(set(m.get('required_figure_ids',[]))-set(uses))
    duplicates=[]
    for value in sorted({r['source']['sha256'] for r in sources}):
        same=[r['id'] for r in sources if r['source']['sha256']==value]
        if len(same)>1:duplicates.append(dict(source_ids=same,sha256=value,action='REVIEW_ONLY_NOT_DELETED_OR_MERGED'))
    profile=dict(status='NOT_PROVIDED')
    if m.get('style_profile'):
        from delivery_review import check_profile
        profile=check_profile(m['style_profile'],manifest_path.parent)
    for row in sources:source(row['source']['path'],row['source']['sha256'])
    source(manifest_path,bound['sha256'])
    return dict(status='READ_ONLY_INTAKE_WITH_PENDING_ITEMS' if pending or uncovered else 'READ_ONLY_INTAKE_RECORDED',
        project_id=m['project_id'],manifest=bound,sources=sources,pending=pending,same_bytes_candidates=duplicates,
        panels=list(panels.values()),figure_uses=list(uses.values()),unaccounted_figure_ids=uncovered,style_profile=profile,
        directory_scan=False,statistics_executed=False,source_files_modified=False,scientific_acceptance='PENDING',production_started=False)


def intake(manifest_path,out):
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    report=inspect_project(manifest_path);save(out/'项目接入清单.json',report)
    lines=['# 项目只读接入清单','',f"项目：{report['project_id']}",'','只检查清单明确列出的文件；没有统计、图像处理或生产。','']
    lines.extend(f"- {r['id']}：{r['kind']}；{r['review_status']}；待核对字段：{', '.join(r['missing_fields']) or '未记录字段缺项（不代表科学已确认）'}；原因：{r['review_reason'] or '无新增待核对声明'}" for r in report['sources'])
    lines.extend(['',f"图号覆盖未记录：{', '.join(report['unaccounted_figure_ids']) or '无清单内遗漏'}",'', 'CONFIRMED为输入声明，不等于本程序审定实验事实。'])
    (out/'从这里开始.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');return report


def finite_positive(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def panel_candidates(manifest_path,out):
    from PIL import Image
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    intake_report=inspect_project(manifest_path);m=read(manifest_path);base=Path(manifest_path).resolve().parent
    sources={r['id']:r for r in intake_report['sources']};panels=intake_report['panels']
    width,height=m['canvas_mm']
    margin=m.get('margin_mm',5);gap=m.get('gap_mm',4);label=m.get('label_band_mm',4)
    if not panels or not all(finite_positive(v) for v in (width,height)) or not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in (margin,gap,label)):
        raise GateError('PANEL_PHYSICAL_DIMENSIONS_INVALID')
    if not finite_positive(m.get('minimum_font_pt',16)):raise GateError('PANEL_MINIMUM_FONT_INVALID')
    columns=m.get('layout_columns',[min(2,len(panels))])
    if not columns or len(columns)>4 or len(set(columns))!=len(columns) or any(type(c) is not int or not 1<=c<=len(panels) for c in columns):
        raise GateError('PANEL_COLUMNS_INVALID')
    crop_groups={};prepared=[];calibrations=[]
    for panel in panels:
        row=sources[panel['source_id']]
        if row['kind'] not in ('data_plot','scientific_image','schematic'):raise GateError('PANEL_EXPECTS_IMAGE_NOT_NUMERICAL_DATA')
        with Image.open(row['source']['path']) as image:
            if image.format not in ('PNG','JPEG') or image.getexif().get(274,1)!=1:raise GateError('PANEL_IMAGE_FORMAT_OR_ORIENTATION_USE_EXISTING_ROUTE')
            w,h=image.size
        crop=panel.get('source_box_px',[0,0,w,h]);content=panel.get('plot_area_normalized',[0,0,1,1])
        if not box_valid(crop,w,h,integer=True) or not box_valid(content,1,1):raise GateError('PANEL_REGION_INVALID')
        if panel.get('crop_group'):
            key=panel['crop_group'];identity=(panel.get('frame_id'),(w,h),tuple(crop))
            if not identity[0]:raise GateError('SHARED_CROP_CONFIRMED_FRAME_REQUIRED')
            if key in crop_groups and crop_groups[key]!=identity:raise GateError('SHARED_CROP_CONFLICT')
            crop_groups[key]=identity
        calibration=panel.get('calibration')
        if calibration:
            if not finite_positive(calibration.get('pixels_per_um')):raise GateError('CALIBRATION_VALUE_INVALID')
            ref=calibration['source'];calibrations.append(source(resolve_file(base,ref['path']),ref['sha256']))
        prepared.append(dict(panel=panel,source=row['source'],crop=crop,content=content,size_px=[w,h],aspect=(crop[2]-crop[0])/(crop[3]-crop[1])))
    candidates=[]
    for count in columns:
        row_count=math.ceil(len(prepared)/count);cw=(width-2*margin-gap*(count-1))/count;ch=(height-2*margin-gap*(row_count-1))/row_count-label
        if min(cw,ch)<=0:raise GateError('PANEL_CANVAS_TOO_SMALL_SPLIT_OR_CHANGE_LAYOUT')
        initial=[]
        for item in prepared:
            iw=min(cw,ch*item['aspect']);ih=iw/item['aspect'];initial.append((iw,ih))
        left=[max((initial[i][0]*prepared[i]['content'][0] for i in range(c,len(prepared),count)),default=0) for c in range(count)]
        right=[max((initial[i][0]*(1-prepared[i]['content'][2]) for i in range(c,len(prepared),count)),default=0) for c in range(count)]
        top=[max(initial[i][1]*prepared[i]['content'][1] for i in range(r*count,min((r+1)*count,len(prepared)))) for r in range(row_count)]
        bottom=[max(initial[i][1]*(1-prepared[i]['content'][3]) for i in range(r*count,min((r+1)*count,len(prepared)))) for r in range(row_count)]
        arranged=[]
        for i,item in enumerate(prepared):
            r,c=divmod(i,count);l,t,rr,b=item['content'];pw,ph=rr-l,b-t
            iw=min((cw-left[c]-right[c])/pw,(ch-top[r]-bottom[r])/ph*item['aspect']);ih=iw/item['aspect']
            if min(iw,ih)<=0:raise GateError('PANEL_CONTENT_ALIGNMENT_IMPOSSIBLE')
            x=margin+c*(cw+gap)+left[c]-iw*l;y=margin+r*(ch+label+gap)+label+ch-bottom[r]-ih*b
            box=[x,y,x+iw,y+ih]
            # Only normalize machine rounding at the physical canvas boundary.
            # Real overflow remains an error; no content is resized to conceal it.
            if min(box[:2]) < -1e-9 or box[2]>width+1e-9 or box[3]>height+1e-9:
                raise GateError('PANEL_LAYOUT_OUTSIDE_CANVAS: '+str(box))
            box=[max(0,box[0]),max(0,box[1]),min(width,box[2]),min(height,box[3])]
            font=item['panel'].get('source_font_pt');source_mm=item['panel'].get('source_width_mm')
            font_check=readable(font,source_mm,iw*72/25.4,m.get('minimum_font_pt',16)) if finite_positive(font) and finite_positive(source_mm) else dict(status='NOT_RECORDED_SOURCE_TEXT_METRICS_REQUIRE_REVIEW')
            arranged.append(dict(panel_id=item['panel']['id'],source=item['source'],source_box_px=item['crop'],
                bbox_mm=box,plot_area_mm=[x+iw*l,y+ih*t,x+iw*rr,y+ih*b],
                label_position_mm=[margin+c*(cw+gap),margin+r*(ch+label+gap)],font_check=font_check,
                review_status=sources[item['panel']['source_id']]['review_status'],native_crop_required=item['crop']!=[0,0,*item['size_px']]))
        candidates.append(dict(id='columns_'+str(count),canvas_mm=[width,height],panels=arranged,
            alignment='DECLARED_PLOT_LEFT_PER_COLUMN_AND_BOTTOM_PER_ROW_ASPECT_PRESERVED',
            automatic_plot_detection=False,scientific_review='PENDING',visual_review='PENDING'))
    for item in prepared:source(item['source']['path'],item['source']['sha256'])
    for ref in calibrations:source(ref['path'],ref['sha256'])
    source(manifest_path,intake_report['manifest']['sha256'])
    result=dict(status='PANEL_LAYOUT_CANDIDATES_NOT_PRODUCTION',project_id=m['project_id'],manifest=intake_report['manifest'],
        candidates=candidates,intake=intake_report,calibration_sources=calibrations,source_pixels_modified=False,production_started=False,author_acceptance='PENDING')
    save(out/'面板布局候选.json',result)
    for candidate in candidates:
        boxes=[]
        for p in candidate['panels']:
            x,y,x1,y1=p['bbox_mm'];a,b,c,d=p['plot_area_mm']
            boxes.extend([f'<rect x="{x}" y="{y}" width="{x1-x}" height="{y1-y}" fill="#eef3f5" stroke="#526873" stroke-width="0.2"/>',
                f'<rect x="{a}" y="{b}" width="{c-a}" height="{d-b}" fill="none" stroke="#0072B2" stroke-width="0.2"/>',
                f'<text x="{x+1}" y="{y+3}" font-size="2.5">{html.escape(p["panel_id"])}</text>'])
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">'+''.join(boxes)+'</svg>'
        (out/('布局预览_'+candidate['id'].split('_')[-1]+'列.svg')).write_text(svg,encoding='utf-8')
    return result
