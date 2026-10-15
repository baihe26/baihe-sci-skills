from paths import *
from core import GateError
def requirements(module,target='illustrator'):
    common=[PYTHON]
    if module=='plot':return common+[PLOT_PY,ORIGIN_PY,PLOT/'phase2c/native.py',PLOT/'phase2c/semantics.py',PLOT/'phase2c_1/qa.py',PLOT/'src/figure_system/persistence.py']
    if module=='designer':return common+[PLOT_PY,DESIGN/'corpus_grounded_design_v1/重放设计.py',HANDOFF/'schemas/figure_spec.schema.json',HANDOFF/'schemas/illustrator_scene_graph.schema.json']
    if module=='ppt' or module=='vector' and target=='ppt':return common+[STUDIO/'03_POC/source/live_studio.py',STUDIO/'03_POC/source/native_finish.py',STUDIO/'03_POC/source/native_audit.py',BACKEND/'src/server.py']+([HANDOFF/'schemas/illustrator_scene_graph.schema.json'] if module=='vector' else [])
    if module=='vector':return common+[PLOT_PY,VECTOR/'bridge/illustrator_bridge.py',VECTOR_HELPERS,DESIGN/'corpus_grounded_design_v1/重放设计.py',HANDOFF/'schemas/illustrator_scene_graph.schema.json']
    raise GateError('MODULE_NOT_RECOGNIZED')
def check(module,target='illustrator'):
    missing=[str(p) for p in requirements(module,target) if not p.is_file()]
    return dict(module=module,target=target,status='FILES_READY_NATIVE_NOT_PROBED' if not missing else 'DEPENDENCY_NOT_CONFIGURED_OR_MISSING',missing=missing)
def require(module,target='illustrator'):
    r=check(module,target)
    if r['missing']:raise GateError(json.dumps(r,ensure_ascii=False))
def report():
    return dict(version='0.1.0',config_present=CONFIG_FILE.is_file(),native_platform='WINDOWS' if os.name=='nt' else 'NOT_WINDOWS_NATIVE_EXECUTION_UNTESTED',routes=[check(m,t) for m,t in [('plot','origin'),('designer','contract'),('vector','illustrator'),('vector','ppt'),('ppt','ppt')]],scope='Only dependency-file presence. Does not start software, install packages, verify licenses, or assert render success.')
