from paths import *
from core import GateError
def portable_check():
    import subprocess
    if not PORTABLE_PY.is_file():return dict(status='DEPENDENCY_NOT_CONFIGURED_OR_MISSING',missing=['portable_python'])
    code="import importlib.util,json;print(json.dumps({x:importlib.util.find_spec(x) is not None for x in ['pptx','PIL']}))"
    result=subprocess.run([str(PORTABLE_PY),'-c',code],capture_output=True,text=True,encoding='utf-8',timeout=20)
    try:modules=json.loads(result.stdout) if result.returncode==0 else {}
    except ValueError:modules={}
    missing=[key for key in ('pptx','PIL') if not modules.get(key)]
    return dict(status='PACKAGES_READY_OFFICE_NOT_REQUIRED' if not missing else 'DEPENDENCY_NOT_CONFIGURED_OR_MISSING',missing=missing,native_probe=False)
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
    return dict(version='0.6.0',config_present=CONFIG_FILE.is_file(),
        configuration=dict(path=str(CONFIG_FILE),selection=CONFIG_SELECTION,running_python=sys.executable,
            configured_module_python=str(PYTHON),explicit_missing=CONFIG_SELECTION=='EXPLICIT_ENVIRONMENT' and not CONFIG_FILE.is_file()),
        writer_locks=dict(owned=[str(p) for p in SHARED_WRITER_LOCKS],legacy_busy_markers=[str(p) for p in DESKTOP_LOCKS]),
        native_platform='WINDOWS' if os.name=='nt' else 'NOT_WINDOWS_NATIVE_EXECUTION_UNTESTED',routes=[check(m,t) for m,t in [('plot','origin'),('designer','contract'),('vector','illustrator'),('vector','ppt'),('ppt','ppt')]],portable=portable_check(),scope='Native routes: file presence only. Optional portable route: Python package availability. No software start, install, license or render assertion.')
