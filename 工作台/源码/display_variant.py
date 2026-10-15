"""Scoped native display copy, source worksheet equality, no altered scientific contract."""
from paths import *
from core import writable,readable
sys.path[:0]=[str(PLOT/'src'),str(PLOT/'vendor/editaplot/runtime/src'),str(PLOT/'scripts')]
from origin_sciplot.origin_backend.execution_context import require_interactive_origin_context
from origin_sciplot.origin_backend.job_queue import origin_job_slot
from origin_sciplot.origin_backend.session import OriginSession
from figure_system.origin_adapter import export_all,output_paths,renderer
from workstation_support import origin_environment
def create(bundle,out,font=10):
    bundle=Path(bundle);out=writable(out)
    if out.exists():raise FileExistsError(out)
    spec=read(bundle/'figure_spec.json');project=next(bundle.glob('*.opju'));h=sha(project)
    out.mkdir(parents=True);require_interactive_origin_context();records=[];baseline=None
    for phase in ['create','reopen']:
        with origin_job_slot(job_kind='workbench-display-variant'):
          with OriginSession(keep_open=False) as session:
            op=session.op;env=origin_environment(session)
            if not env['environment_gate']['pass']:raise RuntimeError('ORIGIN_ENVIRONMENT_GATE')
            assert op.open(str(project if phase=='create' else next(out.glob('*.opju'))))
            before={sh.lt_range(False):sh.to_df().copy(deep=True) for b in op.pages('w') for sh in b}
            if baseline is None:baseline=before
            else:assert before.keys()==baseline.keys() and all(before[k].equals(baseline[k]) for k in before)
            g=op.find_graph(read(bundle/'origin_render_report.json')['readback']['graph']);g.activate();l=g[0]
            if phase=='create':
                code=renderer._origin_font_code(op,'Arial')
                for ax in ('x','y'):l.set_int(ax+'.label.font',code);l.set_float(ax+'.label.pt',font)
                for name in ('xb','yl','legend'):
                    label=l.label(name)
                    if label:label.set_float('fsize',font);label.set_int('font',code)
                # Font enlargement changes the legend's text bounds. Reapply a page anchor afterwards.
                legend=l.label('legend')
                if legend:
                    legend.text=legend.text.replace('    ','  ')
                    op.lt_exec('doc -uw;legend.attach=1;legend.left=page.width*0.035;legend.top=page.height*0.025;')
                op.lt_exec('doc -uw;');assert op.save(str(output_paths(out,spec).result_opju));export_all(op,g,output_paths(out,spec))
            else:
                dest=out/'重开';dest.mkdir();export_all(op,g,output_paths(dest,spec))
            unchanged=all(op.find_sheet('w',name).to_df().equals(df) for name,df in before.items());assert unchanged
            legend=l.label('legend')
            records.append(dict(phase=phase,source_tables_unchanged=unchanged,axis_pt={a:l.get_float(a+'.label.pt') for a in ('x','y')},font_requested=font,legend_bounds={k:legend.get_float(k) for k in ('left','top','width','height')} if legend else None))
    from PIL import Image,ImageChops
    stem=next(out.glob('*.opju')).stem
    a=Image.open(out/(stem+'.png')).convert('RGB');b=Image.open(out/'重开'/(stem+'.png')).convert('RGB')
    assert a.size==b.size and ImageChops.difference(a,b).getbbox() is None
    assert sha(project)==h
    result=dict(status='NATIVE_DISPLAY_VARIANT_VALIDATED_PENDING_VISUAL',parent=source_ref(project),source_figure_spec=source_ref(bundle/'figure_spec.json'),scientific_contract=source_ref(bundle/'PLOT_SEMANTICS_CONTRACT.json'),
        display_override=dict(scope='THIS_ASSET_REVISION_ONLY',font_pt=font,paper_style_unchanged=True,scientific_semantics_unchanged=True),records=records,reopen_png_equal=True,
        final_insert=readable(font,spec['tokens']['width_mm'],600),author_acceptance='PENDING')
    save(out/'显示副本记录.json',result);print(json.dumps(dict(status=result['status']),ensure_ascii=False))
def source_ref(p):return dict(path=str(p),sha256=sha(p))
if __name__=='__main__':create(sys.argv[1],sys.argv[2],float(sys.argv[3]) if len(sys.argv)>3 else 10)
