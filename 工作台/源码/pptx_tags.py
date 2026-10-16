"""PresentationML user-defined tags interoperable with native PowerPoint Tags.

Uses standard custDataLst -> tags relationships, not a name/alt-text imitation.
"""
from paths import Path
from core import GateError
import posixpath, zipfile
from lxml import etree as ET

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
TAGS_TYPE = R + '/tags'
NS = dict(p=P, a=A, r=R)


def xml(blob):
    return ET.fromstring(blob, ET.XMLParser(resolve_entities=False, no_network=True))


def serialized(element):
    return ET.tostring(element, xml_declaration=True, encoding='UTF-8', standalone=True)


def part_target(owner, target):
    result = posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))
    if result.startswith('../') or result.startswith('/'):
        raise GateError('PACKAGE_RELATIONSHIP_OUTSIDE_PACKAGE')
    return result


def rels_name(part):
    return posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')


def read_package(path):
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise GateError('PACKAGE_DUPLICATE_ENTRY')
        return {name: z.read(name) for name in z.namelist()}


def relationships(parts, part):
    name = rels_name(part)
    return {r.get('Id'): r for r in xml(parts[name])} if name in parts else {}


def tags_from(parent, rels, owner, parts):
    tags = parent.find('p:custDataLst/p:tags', NS)
    if tags is None:
        return {}
    ref = rels.get(tags.get('{' + R + '}id'))
    if ref is None or ref.get('Type') != TAGS_TYPE or ref.get('TargetMode') == 'External':
        raise GateError('TAGS_RELATIONSHIP_INVALID')
    rows = xml(parts[part_target(owner, ref.get('Target'))])
    result = {}
    for row in rows:
        key = row.get('name')
        if not key or key in result:
            raise GateError('TAGS_DUPLICATE_OR_EMPTY_KEY')
        result[key] = row.get('val', '')
    return result


def attach_tags(slide, parent, values):
    from pptx.opc.package import Part
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.oxml.ns import qn
    package = slide.part.package
    if parent.find('p:custDataLst', NS) is not None:
        raise GateError('TAGS_ALREADY_PRESENT_PRESERVE_EXISTING')
    body = ET.Element('{' + P + '}tagLst', nsmap={'p': P})
    for key, value in values.items():
        ET.SubElement(body, '{' + P + '}tag', name=str(key), val=str(value))
    name = package.next_partname('/ppt/tags/tag%d.xml')
    part = Part(name, 'application/vnd.openxmlformats-officedocument.presentationml.tags+xml', package, serialized(body))
    rid = slide.part.relate_to(part, TAGS_TYPE)
    container = OxmlElement('p:custDataLst')
    item = OxmlElement('p:tags'); item.set(qn('r:id'), rid); container.append(item)
    # custDataLst precedes extLst in both cSld and nvPr.
    extension = parent.find('p:extLst', NS)
    if extension is None: parent.append(container)
    else: parent.insert(list(parent).index(extension), container)


def shape_nv(shape):
    parent = shape.element[0]
    return parent.find('p:nvPr', NS)


def presentation_locations(path, parts=None):
    parts = read_package(path) if parts is None else parts
    presentation = 'ppt/presentation.xml'
    rels = relationships(parts, presentation)
    rows, slide_ids = [], set()
    for item in xml(parts[presentation]).findall('p:sldIdLst/p:sldId', NS):
        relation = rels[item.get('{' + R + '}id')]
        if relation.get('TargetMode') == 'External': raise GateError('EXTERNAL_SLIDE_UNSUPPORTED')
        part = part_target(presentation, relation.get('Target'))
        root = xml(parts[part]); sr = relationships(parts, part)
        tags = tags_from(root.find('p:cSld', NS), sr, part, parts)
        identity = tags.get('STUDIO_SLIDE_ID')
        if not identity: continue  # Untagged legacy slides remain untouched, not guessed from order.
        if identity in slide_ids: raise GateError('STABLE_SLIDE_ID_AMBIGUOUS')
        slide_ids.add(identity); object_ids = set()
        for element in root.xpath('.//p:sp | .//p:pic | .//p:cxnSp | .//p:grpSp | .//p:graphicFrame', namespaces=NS):
            if not len(element): continue
            nv = element[0].find('p:nvPr', NS)
            if nv is None: continue
            tag = tags_from(nv, sr, part, parts)
            objid = tag.get('STUDIO_ID')
            if not objid: continue
            if objid in object_ids: raise GateError('STABLE_OBJECT_ID_AMBIGUOUS')
            object_ids.add(objid)
            cnv = element[0].find('p:cNvPr', NS)
            rows.append(dict(slide_id=identity, native_slide_id=int(item.get('id')), object_id=objid,
                             native_id=int(cnv.get('id')), native_name=cnv.get('name'),
                             slide_part=part, tags=tag))
    return rows
