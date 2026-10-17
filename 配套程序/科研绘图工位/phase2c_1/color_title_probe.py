from figure_system.common import ROOT,write_new

def run(op,out):
 p=ROOT/'phase2c/runs/closure_20261007_232248/heatmap_compact_labels'
 assert op.open(str(next(p.glob('*.opju'))),readonly=True,asksave=False)
 graph=op.find_graph();graph.activate()
 f=str(ROOT/'phase2c_1/colorscale_format.c');xml=str(out/'native_colorscale_format.xml')
 assert op.lt_exec(f'__p2cCompile=run.LoadOC("{f}");')
 code=op.lt_float('__p2cCompile');print('COMPILE',code,flush=True);assert code==0
 assert op.lt_exec(f'__p2cFormat=p2c1_colorscale_format("{xml}",1,7);')
 result=op.lt_float('__p2cFormat');print('FORMAT',result,flush=True);assert result==1
 graph.save_fig(str(out/'formatted.png'),type='png',width=1417)
 write_new(out/'probe_result.json',{'compile':code,'format':result})
