"""Surgical, copy-only picture updates by native Tags, including nested groups.

Untouched package parts keep their bytes, including media/animations/notes.
This operates on saved files; it does not observe an application's unsaved state.
"""
from paths import Path, read, save, sha, digest
from core import GateError, writable, source
from pptx_tags import P, A, R, PKG, NS, TAGS_TYPE, xml, serialized, read_package, relationships, part_target, rels_name, presentation_locations
from lxml import etree as ET
import zipfile, hashlib, io

CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def canonical(element):
    return ET.tostring(element, method='c14n', exclusive=True).decode('utf-8')


def native_element(root, native_id):
    found = root.xpath('.//p:cNvPr[@id="%s"]' % int(native_id), namespaces=NS)
    if len(found) != 1: raise GateError('NATIVE_ID_MISSING_OR_AMBIGUOUS')
    return found[0].getparent().getparent()


def picture_state(parts, location):
    root = xml(parts[location['slide_part']]); shape = native_element(root, location['native_id'])
    if shape.tag != '{' + P + '}pic': raise GateError('REFERENCE_IS_NOT_PICTURE')
    blips = shape.findall('p:blipFill/a:blip', NS)
    if len(blips) != 1 or blips[0].get('{' + R + '}link'):
        raise GateError('LINKED_OR_COMPLEX_PICTURE_REQUIRES_NATIVE_ROUTE')
    # SVG fallback, OLE, and video pictures must never become ordinary raster images.
    if shape.xpath('.//p:videoFile | .//a:videoFile | .//*[local-name()="svgBlip"] | .//*[local-name()="media"]', namespaces=NS):
        raise GateError('SPECIAL_MEDIA_PICTURE_REQUIRES_NATIVE_ROUTE')
    relation = relationships(parts, location['slide_part']).get(blips[0].get('{' + R + '}embed'))
    if relation is None or relation.get('Type') != R + '/image' or relation.get('TargetMode') == 'External':
        raise GateError('PICTURE_RELATIONSHIP_INVALID')
    media_part = part_target(location['slide_part'], relation.get('Target'))
    blob = parts[media_part]
    ancestry = [canonical(parent.find('p:grpSpPr', NS)) for parent in shape.iterancestors() if parent.tag == '{' + P + '}grpSp']
    size = xml(parts['ppt/presentation.xml']).find('p:sldSz', NS)
    state = dict(shape=canonical(shape), tags=location['tags'], ancestor_transforms=ancestry,
                 media_sha256=hashlib.sha256(blob).hexdigest(), canvas=dict(size.attrib))
    return dict(object_digest=digest(state), media_sha256=state['media_sha256'], media_part=media_part)


def index_references(deck, parts=None):
    deck = Path(deck).resolve(); original=source(deck); parts = read_package(deck) if parts is None else parts
    rows = []
    for loc in presentation_locations(deck, parts):
        tags = loc['tags']
        if not tags.get('ASSET_ID'): continue
        try:
            state=dict(picture_state(parts,loc),update_eligibility='READY_FOR_SAVED_FILE_PICTURE_UPDATE')
        except GateError as error:
            if str(error).split(':')[0] not in ('REFERENCE_IS_NOT_PICTURE','LINKED_OR_COMPLEX_PICTURE_REQUIRES_NATIVE_ROUTE','SPECIAL_MEDIA_PICTURE_REQUIRES_NATIVE_ROUTE'):
                raise
            state=dict(object_digest=None,update_eligibility='NATIVE_ROUTE_REQUIRED',unsupported_reason=str(error))
        rows.append(dict(reference_id=digest(str(deck))[:12] + ':' + loc['slide_id'] + ':' + loc['object_id'],
                         deck=str(deck), slide_id=loc['slide_id'], object_id=loc['object_id'],
                         native_id=loc['native_id'], asset_id=tags['ASSET_ID'], revision=tags.get('ASSET_REVISION'),
                         semantic_sha256=tags.get('SEMANTIC_SHA256'), provenance_sha256=tags.get('PROVENANCE_SHA256'),
                         manual_override=tags.get('HUMAN_OVERRIDE', '').upper() in ('1', 'TRUE', 'YES'),
                         fingerprint_kind='SAVED_OPENXML_PICTURE_AND_ANCESTOR_TRANSFORMS_V1', **state))
    source(deck,original['sha256'])
    return rows


def propagate_request(request_path,out):
    from scientific_gate import resolve_file
    request_path=Path(request_path).resolve();request_source=source(request_path);request=read(request_path)
    base=request_path.parent
    asset=request['new_asset'];semantic=request['semantic_contract']
    asset_path=resolve_file(base,asset['path']);semantic_path=resolve_file(base,semantic['path'])
    source(asset_path,asset['sha256']);source(semantic_path,semantic['sha256'])
    if 'reference_index' in request:
        ref=request['reference_index'];path=resolve_file(base,ref['path']);source(path,ref['sha256'])
        refs=read(path)['references']
        selected=request.get('reference_ids')
        if selected is not None:
            if not selected or len(selected)!=len(set(selected)) or not set(selected)<={r['reference_id'] for r in refs}:raise GateError('SELECTED_REFERENCE_IDS_INVALID')
            refs=[r for r in refs if r['reference_id'] in selected]
    else:refs=request['references']
    source(request_path,request_source['sha256'])
    result=propagate(refs,asset_path,request['new_revision'],out,semantic_path,
                     expected_asset_sha256=asset['sha256'],expected_semantic_sha256=semantic['sha256'])
    save(Path(out)/'更新请求来源.json',dict(request=request_source,new_asset=source(asset_path),semantic_contract=source(semantic_path)))
    return result


def raster_info(blob):
    from PIL import Image
    with Image.open(io.BytesIO(blob)) as image:
        if image.format not in ('PNG', 'JPEG') or getattr(image, 'n_frames', 1) != 1 or image.getexif().get(274, 1) != 1:
            raise GateError('RASTER_UPDATE_REQUIRES_ORIENTED_SINGLE_PNG_JPEG')
        return dict(size=image.size, extension='png' if image.format == 'PNG' else 'jpg',
                    content_type='image/png' if image.format == 'PNG' else 'image/jpeg')


def _add_relation(root, kind, target):
    existing = {r.get('Id') for r in root}; number = 1
    while 'baiheR%d' % number in existing: number += 1
    identity = 'baiheR%d' % number
    ET.SubElement(root, '{' + PKG + '}Relationship', Id=identity, Type=kind, Target=target)
    return identity


def propagate(refs, new_asset, new_revision, out, semantic_contract,expected_asset_sha256=None,expected_semantic_sha256=None):
    """Keep conflicts, update only matching pictures, never resave the source deck."""
    if not refs or not isinstance(new_revision, str) or not new_revision.strip(): raise GateError('UPDATE_REFERENCES_AND_REVISION_REQUIRED')
    keys = [(str(Path(r['deck']).resolve()), r['slide_id'], r['object_id']) for r in refs]
    if len(keys) != len(set(keys)): raise GateError('DUPLICATE_UPDATE_TARGET')
    if len({r['asset_id'] for r in refs}) != 1: raise GateError('ONE_ASSET_PER_UPDATE')
    semantic = source(semantic_contract,expected_semantic_sha256)
    if any(r.get('semantic_sha256') != semantic['sha256'] for r in refs): raise GateError('SCIENTIFIC_SEMANTIC_BINDING_CONFLICT')
    out = writable(out)
    if out.exists(): raise FileExistsError(out)
    asset = source(new_asset,expected_asset_sha256); new_blob = Path(new_asset).read_bytes(); info = raster_info(new_blob)
    if hashlib.sha256(new_blob).hexdigest() != asset['sha256']: raise GateError('ASSET_CHANGED_DURING_READ')
    groups = {}
    for ref in refs: groups.setdefault(str(Path(ref['deck']).resolve()), []).append(ref)
    staged = []
    # Complete preflight before writing any deck, including ambiguity and scientific guards.
    for deck, requested in groups.items():
        original = source(deck); parts = read_package(deck)
        current = {(r['slide_id'], r['object_id']): r for r in index_references(deck, parts)}
        locations = {(r['slide_id'], r['object_id']): r for r in presentation_locations(deck, parts)}
        updates, conflicts = [], []
        for ref in requested:
            key = (ref['slide_id'], ref['object_id']); now = current.get(key)
            if now and now.get('update_eligibility')=='NATIVE_ROUTE_REQUIRED':raise GateError('REFERENCE_NATIVE_ROUTE_REQUIRED: '+ref['reference_id'])
            if ref.get('fingerprint_kind') != 'SAVED_OPENXML_PICTURE_AND_ANCESTOR_TRANSFORMS_V1': raise GateError('REFERENCE_FINGERPRINT_KIND_CONFLICT')
            if now is None:
                conflicts.append(dict(reference_id=ref['reference_id'], reason='STABLE_REFERENCE_MISSING')); continue
            if now['semantic_sha256'] != semantic['sha256']: raise GateError('NATIVE_SEMANTIC_BINDING_CONFLICT')
            if now['asset_id'] != ref['asset_id']: raise GateError('NATIVE_ASSET_ID_CONFLICT')
            if ref.get('manual_override') or now['manual_override'] or now['object_digest'] != ref['object_digest']:
                conflicts.append(dict(reference_id=ref['reference_id'], reason='HUMAN_OVERRIDE_OR_SAVED_OBJECT_CHANGED')); continue
            if now['revision'] == new_revision: raise GateError('REVISION_MUST_ADVANCE')
            old = raster_info(parts[now['media_part']]); old_ratio = old['size'][0] / old['size'][1]
            if abs((info['size'][0] / info['size'][1]) / old_ratio - 1) > .001:
                raise GateError('SCIENTIFIC_IMAGE_ASPECT_CHANGE_REQUIRES_REVIEW')
            updates.append((ref, locations[key]))
        staged.append((deck, original, parts, updates, conflicts))
    out.mkdir(parents=True); results = []
    for deck, original, parts, updates, conflicts in staged:
        before = dict(parts); events = []
        for ref, loc in updates:
            slide_part = loc['slide_part']; root = xml(parts[slide_part]); shape = native_element(root, loc['native_id'])
            relpath = rels_name(slide_part); relroot = xml(parts[relpath])
            media_name = 'ppt/media/baihe_' + asset['sha256'] + '.' + info['extension']
            if media_name in parts and parts[media_name] != new_blob: raise GateError('CONTENT_ADDRESSED_MEDIA_CONFLICT')
            parts[media_name] = new_blob
            rid = _add_relation(relroot, R + '/image', '../media/' + Path(media_name).name)
            shape.find('p:blipFill/a:blip', NS).set('{' + R + '}embed', rid)
            # Preserve the historical provenance separately. A new raster is not silently
            # certified as the pixels referred to by the old source chain.
            tags = dict(loc['tags']); previous = tags.pop('PROVENANCE_SHA256', None)
            if previous: tags['PREVIOUS_PROVENANCE_SHA256'] = previous
            tags.update(ASSET_REVISION=new_revision, ASSET_SOURCE_SHA256=asset['sha256'],
                        PROVENANCE_STATUS='REPLACEMENT_PIXELS_PENDING_SOURCE_REVIEW')
            event = dict(reference_id=ref['reference_id'], previous_revision=ref['revision'], revision=new_revision,
                         asset=asset, semantic_contract=semantic, previous_provenance_sha256=previous)
            tags['ASSET_UPDATE_SHA256'] = digest(event); events.append(event)
            tagpart = 'ppt/tags/baihe_' + digest(event) + '.xml'
            tagroot = ET.Element('{' + P + '}tagLst', nsmap={'p': P})
            for key, value in tags.items(): ET.SubElement(tagroot, '{' + P + '}tag', name=key, val=str(value))
            parts[tagpart] = serialized(tagroot)
            rid = _add_relation(relroot, TAGS_TYPE, '../tags/' + Path(tagpart).name)
            shape[0].find('p:nvPr/p:custDataLst/p:tags', NS).set('{' + R + '}id', rid)
            parts[slide_part] = serialized(root); parts[relpath] = serialized(relroot)
            types = xml(parts['[Content_Types].xml'])
            if not any(q.get('Extension', '').lower() == info['extension'] for q in types):
                ET.SubElement(types, '{' + CT + '}Default', Extension=info['extension'], ContentType=info['content_type'])
            ET.SubElement(types, '{' + CT + '}Override', PartName='/' + tagpart, ContentType='application/vnd.openxmlformats-officedocument.presentationml.tags+xml')
            parts['[Content_Types].xml'] = serialized(types)
        # Check every unselected native object before packaging. Other parts are
        # copied byte-for-byte; no round trip through an Office/library serializer.
        selected = {(loc['slide_part'], loc['native_id']) for _, loc in updates}
        for part in {loc['slide_part'] for _, loc in updates}:
            oldroot, newroot = xml(before[part]), xml(parts[part])
            for identity in selected:
                if identity[0] != part: continue
                for root in (oldroot, newroot):
                    item = native_element(root, identity[1]); item.getparent().remove(item)
            if canonical(oldroot) != canonical(newroot): raise GateError('UNRELATED_NATIVE_OBJECT_CHANGED')
        destination = out / (Path(deck).stem + '_' + digest(deck)[:8] + '_新版本.pptx')
        if updates:
            source(deck, original['sha256']); source(new_asset, asset['sha256']); source(semantic_contract, semantic['sha256'])
            with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as z:
                for name, blob in parts.items(): z.writestr(name, blob)
            reread = index_references(destination)
            for ref, _ in updates:
                found = [r for r in reread if (r['slide_id'], r['object_id']) == (ref['slide_id'], ref['object_id'])]
                if len(found) != 1 or found[0]['revision'] != new_revision or found[0]['media_sha256'] != asset['sha256']:
                    raise GateError('UPDATED_PACKAGE_READBACK_CONFLICT')
        source(deck, original['sha256'])
        results.append(dict(source=original, output=source(destination) if updates else None,
                            updated=[r['reference_id'] for r, _ in updates], conflicts=conflicts, events=events,
                            unchanged_original_parts=[name for name in before if parts[name] == before[name]],
                            changed_original_parts=[name for name in before if parts[name] != before[name]],
                            unrelated_objects_equal=True, original_media_bytes_preserved=True))
    report = dict(status='COPIES_WRITTEN_PENDING_NATIVE_VISUAL_REVIEW' if any(r['updated'] for r in results) else 'NO_MATCHING_UPDATES_CONFLICTS_PRESERVED', asset=asset, semantic_contract=semantic,
                  revision=new_revision, results=results, source_files_unchanged=True,
                  unsaved_application_state='NOT_INSPECTED_SAVED_FILES_ONLY', automatic_retry=False,
                  scientific_review='PENDING', author_acceptance='PENDING')
    save(out / '引用传播结果.json', report)
    return report
