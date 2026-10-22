"""Pure input/skeleton gate shared by native and optional portable production."""
from paths import Path, read, save, sha
from core import writable, GateError
from scientific_gate import validate_pack, validate_design
from layout_checks import check_layout
from evidence_adapter import check_evidence
from asset_contract import check_assets, check_reconstruction
from pack_files import fingerprint


def inspect_pack(scene_path):
    scene_path=Path(scene_path).resolve();base=scene_path.parent
    consistency=validate_pack(scene_path);graph=read(scene_path);spec=read(base/'FigureSpec.json')
    from color_roles import check_roles
    roles=check_roles(read(base/'color_roles.json'),graph) if (base/'color_roles.json').is_file() else None
    from delivery_review import check_profile, check_requirements
    profile=check_profile(read(base/'style_profile.json'),base) if (base/'style_profile.json').is_file() else dict(status='NOT_PROVIDED')
    goals=check_requirements(read(base/'delivery_requirements.json'),graph) if (base/'delivery_requirements.json').is_file() else []
    layout=check_layout(graph,read(base/'layout_constraints.json') if (base/'layout_constraints.json').is_file() else None)
    if layout['status']!='PASS': raise GateError('LAYOUT_CONSTRAINT_FAILED: '+str(layout['findings']))
    assets=check_assets(read(base/'retained_assets.json'),base,graph) if (base/'retained_assets.json').is_file() else dict(status='PASS',assets=[],source_union_coverage=[])
    reconstruction=check_reconstruction(read(base/'reconstruction_map.json'),base,graph,assets) if (base/'reconstruction_map.json').is_file() else dict(status='NOT_PROVIDED')
    evidence=check_evidence(read(base/'evidence_map.json'),base,spec) if (base/'evidence_map.json').is_file() else dict(status='NOT_PROVIDED')
    return dict(status='PASS_WITH_UNRESOLVED_REVIEW' if reconstruction['status']=='NEEDS_REVIEW' else 'PASS',
                scene_sha256=sha(scene_path),input_fingerprint=fingerprint(scene_path),consistency=consistency,layout=layout,retained_assets=assets,
                reconstruction=reconstruction,evidence=evidence,style_profile=profile,delivery_observations=len(goals),color_roles=dict(status='DECLARED_BINDINGS_CHECKED' if roles is not None else 'NOT_PROVIDED_COLOR_MEANING_UNKNOWN',count=len(roles or {})),scientific_truth='NOT_ASSESSED',author_acceptance='PENDING')


def preflight(out,scene=None,spec=None,plan=None,binding=None):
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    if scene: report=inspect_pack(scene)
    elif spec and plan and binding:
        report=dict(status='PASS',consistency=validate_design(read(spec),read(plan),read(binding),Path(spec).parent,Path(binding).parent),
                    stage='SCIENCE_SKELETON_ONLY',production_started=False,scientific_truth='NOT_ASSESSED')
    else:raise GateError('PREFLIGHT_INPUT_REQUIRED')
    save(out/'生产前检查.json',report)
    return report
