"""Exact straight rectangle bindings through nested groups, without rerouting paths."""


def rectangle_connector_plan(graph, tolerance=1e-6):
    objects = {o['id']: o for o in graph['objects']}
    links = graph['parent_child']
    def candidates(owner):
        ids = set(); pending = [owner]
        while pending:
            current = pending.pop()
            if current in ids: continue
            ids.add(current)
            pending.extend(x['child_id'] for x in links if x['parent_id'] == current)
        return [objects[key] for key in ids if key in objects and objects[key]['geometry']['kind'] == 'RECT']
    def straight(points):
        if len(points) < 2: return False
        begin,end=points[0],points[-1];dx,dy=end[0]-begin[0],end[1]-begin[1]
        length2=dx*dx+dy*dy
        if length2 <= tolerance*tolerance: return False
        previous=-tolerance
        for point in points:
            x,y=point[0]-begin[0],point[1]-begin[1]
            # The intermediate nodes must lie on, and progress along, the same segment.
            if abs(x*dy-y*dx)>tolerance*length2**.5:return False
            progress=(x*dx+y*dy)/length2
            if progress < previous-tolerance or not -tolerance <= progress <= 1+tolerance:return False
            previous=progress
        return True
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
        if not straight(points) or data.get('encoding') not in ('solid_arrow','dashed_arrow'):
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
