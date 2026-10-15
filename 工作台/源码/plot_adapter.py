from paths import *
from core import writable,source,GateError
import shutil,subprocess
def render_bundle(bundle,out):
    """Existing approved Phase2C bundle only; no new statistics or inferred mapping."""
    bundle=Path(bundle).resolve();out=writable(out)
    if out.exists():raise FileExistsError(out)
    # Validate before any Origin activation.
    sys.path[:0]=[str(PLOT/'src'),str(PLOT)]
    from phase2c.semantics import validate,validate_render_plan,validate_style_owner
    contract=read(bundle/'PLOT_SEMANTICS_CONTRACT.json');spec=read(bundle/'figure_spec.json')
    validate(contract,bundle);validate_render_plan(contract,spec,bundle);validate_style_owner(contract,spec)
    if contract.get('data_status')!='SYNTHETIC_NO_SCIENTIFIC_CONCLUSION':
        raise GateError('REAL_DATA_PRODUCTION_REQUIRES_TASK_SPECIFIC_AUTHORIZATION_AND_ADAPTER')
    out.mkdir(parents=True)
    for name in ['figure_spec.json','PLOT_SEMANTICS_CONTRACT.json','analysis_manifest.json','plot_data.csv','observations.csv','PLOT_DECISION_RECORD.json']:
        p=bundle/name
        if p.exists():shutil.copy2(p,out/name)
    sources={str(p):sha(p) for p in bundle.iterdir() if p.is_file()}
    worker=ROOT/'源码/origin_worker.py'
    for mode,d in [('render',out),('reopen',out/'independent_reopen')]:
        if mode=='reopen':
            d.mkdir();project=next(out.glob('*.opju'));save(d/'request.json',dict(bundle=str(out),project=str(project),project_sha256=sha(project)))
        with (d/'运行.log').open('x',encoding='utf-8') as f:
            # No hard timeout: worker may own Origin. Poll the process without killing it.
            r=subprocess.run([str(ORIGIN_PY),str(worker),mode,str(d)],stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONUTF8='1'))
        if r.returncode:raise RuntimeError('ORIGIN_FAILED: '+str(d/'运行.log'))
    from figure_system.persistence import compare_native_and_rendered
    from phase2c_1.qa import exports as inspect_exports,bar_geometry
    from phase2c.acceptance import inspect_bundle
    fresh=read(out/'origin_render_report.json')['readback'];opened=read(out/'independent_reopen/reopen_report.json')['readback']
    # Existing acceptance reads the original historical directory name.
    # Use separate, explicit inputs rather than renaming/overwriting source reports.
    persist=compare_native_and_rendered(fresh,opened,out,out/'independent_reopen')
    stem=next(out.glob('*.opju')).stem
    qa=inspect_exports(out/(stem+'.pdf'),out/(stem+'.svg'),spec)
    semantic_qa=inspect_bundle(out,read(PLOT/'phase2c/NATIVE_COLOR_REFERENCE.json')['codes_from_official_Origin_ocolor'],bar_geometry=bar_geometry)
    report=dict(source_unchanged=all(Path(p).is_file() and sha(p)==h for p,h in sources.items()),scientific_contract_sha256=sha(out/'PLOT_SEMANTICS_CONTRACT.json'),
        source_values_equal=fresh['source_all_values_equal'] and opened['source_all_values_equal'],persistence=persist,exports=qa,semantic_qa=semantic_qa,native_edit_probe=read(out/'independent_reopen/native_edit/edit_report.json'),
        native_readback=True,visual='PENDING',author_acceptance='PENDING',status='NATIVE_RUN_COMPLETE_PENDING_REVIEW')
    save(out/'整合验证.json',report);return report
if __name__=='__main__':print(json.dumps(render_bundle(sys.argv[1],sys.argv[2]),ensure_ascii=False,indent=2))
