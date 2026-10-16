"""Exact dependency allowlist for source protection and revision fingerprints."""
from paths import Path,read,sha,digest
from scientific_gate import resolve_file

SIDECARS=('FigureSpec.json','ConstructionPlan.json','scientific_binding.json','layout_constraints.json',
          'retained_assets.json','reconstruction_map.json','evidence_map.json','修订记录.json')


def dependency_paths(scene_path):
    scene_path=Path(scene_path).resolve();base=scene_path.parent
    paths={scene_path,*[base/name for name in SIDECARS if (base/name).is_file()]}
    spec=read(base/'FigureSpec.json');binding=read(base/'scientific_binding.json')
    refs=[v['path'] for v in spec['metadata']['sources']]+[binding['source_file']['path']]
    if (base/'retained_assets.json').is_file():refs.extend(r['source']['path'] for r in read(base/'retained_assets.json')['assets'])
    if (base/'reconstruction_map.json').is_file():refs.append(read(base/'reconstruction_map.json')['source']['path'])
    if (base/'evidence_map.json').is_file():refs.extend(r['path'] for r in read(base/'evidence_map.json')['source_blocks'])
    paths.update(resolve_file(base,ref) for ref in refs)
    return sorted(paths)


def fingerprint(scene_path):
    base=Path(scene_path).resolve().parent
    return digest([dict(path=p.relative_to(base).as_posix() if p.is_relative_to(base) else str(p),sha256=sha(p)) for p in dependency_paths(scene_path)])
