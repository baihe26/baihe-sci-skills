"""Select only exact straight rectangle-edge bindings; preserve other path geometry."""


def rectangle_connector_plan(graph, tolerance=1e-6):
    objects = {o['id']: o for o in graph['objects']}
    links = graph['parent_child']
    def candidates(owner):
        ids = {owner} | {x['child_id'] for x in links if x['parent_id'] == owner}
        return [objects[key] for key in ids if key in objects and objects[key]['geometry']['kind'] == 'RECT']
    def anchor(owner, point):
        matches = []
        for obj in candidates(owner):
            d = obj['geometry']['data']; x, y, w, h = (d[k] for k in ('x','y','width','height'))
            for site, xy in ((1,(x+w/2,y)), (2,(x,y+h/2)), (3,(x+w/2,y+h)), (4,(x+w,y+h/2))):
                if max(abs(point[i]-xy[i]) for i in (0,1)) <= tolerance:
                    matches.append(dict(object_id=obj['id'], site=site))
        return matches[0] if len(matches) == 1 else None
    result = {}
    for arrow in graph['arrow_objects']:
        data = arrow['geometry']['data']; points = data.get('points', [])
        if len(points) != 2 or data.get('encoding') not in ('solid_arrow','dashed_arrow'):
            continue
        source = anchor(arrow['source_id'], points[0]); target = anchor(arrow['target_id'], points[-1])
        if source and target:
            result[arrow['id']] = dict(source=source, target=target)
    return result


def bind_native(slide, plans, children):
    shapes = {q.Name: q for q in children(slide.Shapes)}
    result = []
    for identity, plan in plans.items():
        shape = shapes[identity]; connector = shape.ConnectorFormat
        connector.BeginConnect(shapes[plan['source']['object_id']], plan['source']['site'])
        connector.EndConnect(shapes[plan['target']['object_id']], plan['target']['site'])
        if not connector.BeginConnected or not connector.EndConnected:
            raise ValueError('NATIVE_CONNECTOR_BINDING_FAILED: ' + identity)
        result.append(dict(id=identity, source_object=connector.BeginConnectedShape.Name,
                           target_object=connector.EndConnectedShape.Name,
                           begin_site=connector.BeginConnectionSite, end_site=connector.EndConnectionSite))
    return result
