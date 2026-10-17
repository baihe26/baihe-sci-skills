"""Handoff prose derives from the current contract, never a case-name template."""


def build_drawability_plan(spec):
    parts = ['live text and relation objects', 'semantic groups', 'procedural vector detail']
    assets = spec.get('asset_requirements', [])
    if assets:
        parts.append('asset requirements declared in FigureSpec: ' + ', '.join(
            f'{asset["id"]} ({asset["editable_type"]})' for asset in assets
        ))
        parts.append('asset placement only when declared in the SceneGraph')
    else:
        parts.append('no asset requirements declared in FigureSpec')
    parts.append('no final production')
    return '; '.join(parts)


def build_local_qa_gate(spec):
    return [
        'all ids resolve; no new relation ids',
        'uncertain/proposed/goal never solid causal edges',
        *spec.get('scientific_constraints', []),
        'text live + move/group/edit/save-reopen contracts only; native not executed',
    ]
