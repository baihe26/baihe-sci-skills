"""Thin native-archetype adapter. All rendering/export/lifecycle remains upstream."""
from pathlib import Path
from dataclasses import replace
import json, traceback
import numpy as np, pandas as pd
from figure_system.common import ROOT,read,sha,write_new,require_hash
from figure_system.origin_adapter import renderer,AdaptiveOriginStyle,ScientificSeries,ScientificAxisPlan,ScientificDisplayPlan,ScientificPlotSpec,ScientificPreparation,output_paths,export_all,plot_command,SYMBOL
from origin_sciplot.origin_backend import evidence_renderer as er, categorical_renderer as cr
from .semantics import validate

def prepare(spec,out):
 frame=pd.read_csv(out/"plot_data.csv",float_precision="round_trip")
 t=spec["tokens"]
 style=AdaptiveOriginStyle(profile_name=spec["style_version"],page_width_cm=t["width_mm"]/10,page_height_cm=t["height_mm"]/10,
  layer_left_percent=t["layer_left_percent"],layer_top_percent=t["layer_top_percent"],layer_width_percent=t["layer_width_percent"],layer_height_percent=t["layer_height_percent"],
  font_family=t["font_family"],axis_title_size_pt=t["axis_title_pt"],tick_label_size_pt=t["tick_pt"],legend_size_pt=t["legend_pt"],
  plot_line_width_pt=t["line_width_pt"],frame_line_width_pt=t["axis_width_pt"],major_tick_length_pt=t["tick_length_pt"],
  minor_tick_length_pt=0,error_bar_width_pt=t["error_width_pt"],fill_transparency_percent=spec.get("native_bar_fill_transparency_percent",0),heatmap_palette="Viridis.PAL")
 series=tuple(ScientificSeries(s["y"],s["y"],error_column=s.get("error"),error_kind=read(out/"PLOT_SEMANTICS_CONTRACT.json")["uncertainty"]["type"] if s.get("error") else None,group=s["group_id"]) for s in spec["series"])
 kind={"violin":"violin","histogram":"histogram","heatmap":"heatmap","box":"box"}.get(spec["backend_route"],"line_error")
 bins=spec.get("bins") or {}
 plot=ScientificPlotSpec(plot_kind=kind,plot_mode=kind,x_column=spec["series"][0].get("x"),category_column=spec.get("category_column"),
  series=series,x_title=spec["x_title"],y_title=spec["y_title"],y2_title=None,x_scale=spec["x_scale"],y_scale=spec["y_scale"],display_transform="identity",
  display_plan=ScientificDisplayPlan(t["marker_size_pt"],.72,.8,figure_style=style),axis_plan=ScientificAxisPlan(*spec["x_limits"],*spec["y_limits"]),
  bin_rule="APPROVED_EXPLICIT" if bins else None,bin_begin=bins.get("begin"),bin_end=bins.get("end"),bin_size=bins.get("size"))
 prep=ScientificPreparation(template_id=kind,source_path=str(out/"plot_data.csv"),source_sha256=sha(out/"plot_data.csv"),source_size_bytes=(out/"plot_data.csv").stat().st_size,
  source_format="csv",source_sheet=None,source_columns=tuple(frame.columns),row_count=len(frame),ignored_empty_rows=0,
  assignments=tuple((c,"approved") for c in frame),plot_spec=plot,confidence=1.,requires_confirmation=False,
  confirmation_reasons=(),warnings=("USER_AUTHORIZED_SYNTHETIC_PHASE2C_ONLY",),mapping_confirmed=True,plan_digest=sha(out/"figure_spec.json"))
 return frame,style,prep

def build_box(op,frame,prep):
 # Official Origin plotgboxraw; no quartile/KDE algorithm is implemented here.
 sheet=op.new_sheet("w",lname="Box approved independent units");sheet.from_df(frame);sheet.cols_axis("y");sheet.activate()
 assert op.lt_exec(f'plotgboxraw irng:={sheet.lt_range(False)}!1:{len(prep.plot_spec.series)} num:=1 g1:="Long Name" sort:=0;')
 graph=op.find_graph();layer=graph[0];layer.group(False)
 renderer._apply_page_layer(op,graph,layer,dual_y=False,preparation=prep)
 er._style_evidence_axes(op,layer,prep,x_numeric=False,y_numeric=True)
 layer.axis("x").set_limits(*[.5,len(prep.plot_spec.series)+.5,1])
 layer.axis("y").set_limits(prep.plot_spec.axis_plan.y_from,prep.plot_spec.axis_plan.y_to,prep.plot_spec.axis_plan.y_step)
 er._style_titles(op,graph,layer,prep)
 return graph,{"implementation":"Origin official plotgboxraw; approved native box geometry"}

def source_roundtrip(op,out):
 obs=pd.read_csv(out/"observations.csv",float_precision="round_trip")
 sheet=op.new_sheet("w",lname="Original independent units and hierarchy");sheet.from_df(obs)
 return sheet.lt_range(False)

def table(spec,frame):
 plans=[]
 for index,s in enumerate(spec["series"]):
  g=spec["all_groups"][s["group_id"]]
  label=g["display_name"] if sum(i["group_id"]==s["group_id"] for i in spec["series"])==1 else g["display_name"]+" "+s["y"]
  marker=0 if s["plot_type"]=="l" else spec["tokens"]["raw_marker_size_pt"] if s["role"] in ("unit","unit_summary") else spec["tokens"]["marker_size_pt"]
  plans.append(renderer.OriginSeriesPlan(s["y"],s["y"],s["x"],s.get("error"),label,"left",s["plot_type"],g["edge"],45 if s["plot_type"]=="c" else None,marker,
   is_reference=s.get("individual_trace",False) or s["role"]=="approved_fit" or s["y"].endswith("_raw"),symbol_kind=SYMBOL[g["marker"]],
   transparency_percent=55 if s.get("individual_trace") else spec.get("native_bar_fill_transparency_percent",0) if s["plot_type"]=="c" else 0))
 return renderer.OriginTablePlan(frame,spec["series"][0]["x"],spec.get("category_column"),tuple(plans),())

def apply_b(op,graph,spec,prep):
 graph.activate();layer=graph[0];t=spec["tokens"]
 layer.group(False)
 op.lt_exec("layer -b f 0;")
 for axis in ("x","y"):
  layer.set_int(f"{axis}.showAxes",1);layer.set_int(f"{axis}.ticks",2);layer.set_int(f"{axis}.minorTicks",0)
  layer.set_float(f"{axis}.tickthickness",t["tick_width_pt"]);layer.set_float(f"{axis}.ticklength",t["tick_length_pt"])
  layer.set_int(f"{axis}.showGrids",0);layer.set_float(f"{axis}.thickness",t["axis_width_pt"])
  layer.set_float(f"{axis}.label.pt",t["tick_pt"])
  layer.axis(axis).title=spec[axis+"_title"]
  label=layer.label("xb" if axis=="x" else "yl")
  label.text=spec[axis+"_title"];label.set_int("bold",0);label.set_float("fsize",t["axis_title_pt"])
  label.set_int("font",renderer._origin_font_code(op,t["font_family"]));label.set_int("show",1)
 if spec["backend_route"] in ("box","violin") or spec["plot_kind"]=="bar_raw":
  labels=op.new_sheet("w",lname="Stable group labels");labels.from_list(0,[spec["all_groups"][gid]["display_name"] for gid in dict.fromkeys(s["group_id"] for s in spec["series"])])
  graph.activate()
  assert op.lt_exec(f'range __p2cLabels={labels.lt_range(False)}!col(1);axis -ps X T __p2cLabels;')
  layer.axis("x").set_limits(*spec["x_limits"])
 if spec["backend_route"] in ("box","violin","histogram"):
  for i,s in enumerate(spec["series"],1):
   g=spec["all_groups"][s["group_id"]]
   plot_command(op,graph,i,f'-c {op.ocolor(g["edge"])}')
   plot_command(op,graph,i,f'-fc {op.ocolor(g["fill"])}')
   layer.set_int(f"plot{i}.symbol.kind",SYMBOL[g["marker"]])
   layer.set_int(f"plot{i}.symbol.interior",0)
   if spec["backend_route"] in ("box","violin"):
    layer.set_int(f"plot{i}.boxchart.line",2)
    layer.set_float(f"plot{i}.symbol.size",t["raw_marker_size_pt"])
    # Raw unit evidence is added with upstream native scatter primitive.
    if spec["backend_route"] in ("box","violin"):
     rawsheet=op.new_sheet("w",lname="Box raw independent points")
     vals=pd.read_csv(prep.source_path,float_precision="round_trip")[s["y"]].dropna().tolist()
     rawsheet.from_df(pd.DataFrame({"X":i+np.linspace(-.12,.12,len(vals)),s["y"]:vals}))
     p=renderer.OriginSeriesPlan(s["y"],s["y"],"X",None,g["display_name"]+" raw","left","s",g["edge"],None,t["raw_marker_size_pt"],symbol_kind=SYMBOL[g["marker"]],transparency_percent=25)
     renderer._add_plot(layer,rawsheet,p,"X",renderer._figure_style(prep))
 graph.activate()
 layer.group(False)
 if spec["backend_route"]!="heatmap":
  layer.set_float("x.label.rotate",0)
  layer.set_int("x.label.table",0);layer.set_int("y.label.table",0)
 if spec["plot_kind"]=="paired_dot_slope":layer.axis("x").set_limits(*spec["x_limits"])
 catalog=dataset_catalog(op,spec)
 for idx,native_plot in enumerate(layer.obj.DataPlots,1):
  entry=catalog.get(native_plot.GetName())
  if entry:
   w,cols,series,role,col=entry;g=spec["all_groups"][series["group_id"]]
   # Direct documented Layer.PlotN properties avoid compound-plot GetIndex aliases.
   layer.set_int(f"plot{idx}.color",op.ocolor(g["edge"]))
   if int(layer.get_int(f"plot{idx}.pid")) in (201,202):
    layer.set_int(f"plot{idx}.symbol.kind",SYMBOL[g["marker"]])
    layer.set_int(f"plot{idx}.symbol.interior",0)
 for idx in range(1,len(list(layer.obj.DataPlots))+1):
  pid=int(layer.get_int(f"plot{idx}.pid"))
  if pid==203:
   plot_command(op,graph,idx,"-paap 1")
   layer.set_float(f"plot{idx}.transparency",spec.get("native_bar_fill_transparency_percent",0))
  if pid==231:plot_command(op,graph,idx,f'-z {t["error_cap_pt"]}')
  if pid in (201,202):
   color=float(layer.get_float(f"plot{idx}.color"))
   for g in spec["groups"].values():
    if color==op.ocolor(g["edge"]):
     plot_command(op,graph,idx,"-kf 0");plot_command(op,graph,idx,f'-csf {op.ocolor(g["fill"])}')
 # Legend entries come from stable group identities, never numeric series order.
 if spec["backend_route"]!="heatmap":
  entries=[]
  for gid,g in spec["groups"].items():
   candidates=[i for i,s in enumerate(spec["series"],1) if s["group_id"]==gid and not s.get("individual_trace") and s["role"]!="approved_fit"]
   if candidates:
    # Error plots increase native indices; dataset identity will supply the final map.
    entries.append((gid,g))
  legend=layer.label("legend")
  if legend is None:
   op.lt_exec('legend;');legend=layer.label("legend")
  if legend is not None:
   indexes=[]
   for gid,g in entries:
    for idx,p in sorted(enumerate(layer.obj.DataPlots,1),key=lambda pair:0 if int(layer.get_int(f"plot{pair[0]}.pid"))==(201 if spec["backend_route"] in ("box","violin") else 202) else 1):
     if float(layer.get_float(f"plot{idx}.color"))==op.ocolor(g["edge"]):
      indexes.append((idx,g));break
   legend.text="    ".join(r"\L("+str(i)+") "+g["display_name"] for i,g in indexes)
   legend.set_float("fsize",t["legend_pt"]);legend.set_int("bold",0);legend.set_int("showframe",0);legend.set_int("font",renderer._origin_font_code(op,t["font_family"]))
   op.lt_exec("legend.attach=1;legend.left=page.width*0.18;legend.top=page.height*0.04;")
 if read(Path(prep.source_path).parent/"PLOT_SEMANTICS_CONTRACT.json")["connection"]["mode"]=="ecdf":
  for idx in range(1,len(list(layer.obj.DataPlots))+1):
   plot_command(op,graph,idx,"-l 11")  # Official Step Horz: right-continuous ECDF, no interpolation.
 op.lt_exec("doc -uw;")
 renderer._position_axis_titles_on_page(op,layer,{"x_title":layer.label("xb"),"y_title":layer.label("yl")})
 op.lt_exec("doc -uw;")


def dataset_catalog(op,spec):
 catalog={}
 for w in [s for b in op.pages("w") for s in b]:
  cols=list(w.to_df().columns)
  seen=set()
  for series in spec["series"]:
   for role,col in ((series["role"],series["y"]),("approved_error",series.get("error"))):
    if col is not None and col in cols and col not in seen:
     seen.add(col)
     catalog[er._shap_origin_dataset_name(w,cols.index(col))]=(w,cols,series,role,col)
 return catalog

def finite_values(values):
 return [None if isinstance(v,(float,np.floating)) and not np.isfinite(v) else v for v in values]

def inspect_native(op,graph,spec,out,source_sheet,mapping=None):
 graph.activate();layer=graph[0];plots=[];sheets=[s for b in op.pages("w") for s in b]
 catalog=dataset_catalog(op,spec)
 for idx,p in enumerate(layer.obj.DataPlots,1):
  actual=p.GetName();pid=int(layer.get_int(f"plot{idx}.pid"));binding=None
  if actual in catalog:
   w,cols,series,role,col=catalog[actual]
   binding={"worksheet":w.lt_range(False),"column":col,"role":role,"group_id":series["group_id"],"expected":actual,
    "values":finite_values(w.to_list(cols.index(col))),"x_column":series.get("x"),
    "x_values":finite_values(w.to_list(cols.index(series["x"]))) if series.get("x") in cols else None}
  if binding and series.get("x") in cols and pid in (200,201,202,203):
   binding["actual_native_xy"] = er._read_shap_plot_binding(op,layer,f"[{graph.name}]1!{idx}",w,cols.index(series["x"]),cols.index(col),prefix=f"p2c1_{idx}")
  props={k:float(layer.get_float(f"plot{idx}."+k)) for k in ("color","symbol.size","transparency")}
  if read(out/"PLOT_SEMANTICS_CONTRACT.json")["connection"]["mode"]=="ecdf":
   assert op.lt_exec(f'range __p2cECDF=[{graph.name}]1!{idx};get __p2cECDF -l __p2cConnection;')
   props["line_connection"]=float(op.lt_float("__p2cConnection"))
   assert props["line_connection"]==11,"ECDF must use native horizontal steps"
  plots.append({"index":idx,"pid":pid,"dataset":actual,"binding":binding,"properties":props})
 matrix=None
 if spec["backend_route"]=="heatmap":
  m=next(s for b in op.pages("m") for s in b)
  expected=pd.read_csv(out/"plot_data.csv",float_precision="round_trip")[[s["y"] for s in spec["series"]]].to_numpy()
  actual=m.to_np2d()
  assert np.allclose(actual,expected,rtol=0,atol=1e-12)
  matrix={"worksheet":m.lt_range(False),"data":actual.tolist(),"source_equal":True,"xymap":list(m.xymap)}
 else:
  assert all(p["binding"] for p in plots),"Native dataset identity could not be verified"
 source=op.find_sheet("w",source_sheet);expected=pd.read_csv(out/"observations.csv",float_precision="round_trip");actual=source.to_df()
 for c in expected:
  if pd.api.types.is_numeric_dtype(expected[c]):assert np.allclose(actual[c],expected[c],rtol=0,atol=1e-12),c
  else:assert actual[c].astype(str).tolist()==expected[c].astype(str).tolist(),c
 axes={axis:{k:float(layer.get_float(f"{axis}.{k}")) for k in ("from","to","inc","type","label.pt","thickness","ticks","ticklength","showAxes","showGrids")} for axis in ("x","y")}
 titles={axis:layer.axis(axis).title for axis in ("x","y")}
 return {"graph":graph.name,"plots":plots,"matrix":matrix,"source_sheet":source_sheet,"source_all_values_equal":True,"source_rows":len(expected),"axes":axes,"titles":titles,
 "title_geometry":renderer._title_geometry(op,{"x_title":layer.label("xb"),"y_title":layer.label("yl")}),
 "actual_page_mm":{"width":op.lt_float("page.width/page.resx*25.4"),"height":op.lt_float("page.height/page.resy*25.4")}}

def render(op,out):
 spec=read(out/"figure_spec.json");contract=read(out/"PLOT_SEMANTICS_CONTRACT.json");validate(contract,out)
 from .semantics import validate_render_plan,validate_style_owner
 validate_render_plan(contract,spec,out);validate_style_owner(contract,spec)
 require_hash(out/"PLOT_SEMANTICS_CONTRACT.json",spec["contract_sha256"])
 require_hash(ROOT/"fixtures/styles/style_v0_1_selected.json",spec["style_sha256"])
 frame,style,prep=prepare(spec,out);source_sheet=source_roundtrip(op,out);route=spec["backend_route"]
 if route=="violin":graph,upstream=er._build_distribution_graph(op,frame,prep)
 elif route=="box":graph,upstream=build_box(op,frame,prep)
 elif route=="histogram":graph,upstream=er._build_histogram_graph(op,frame,prep)
 elif route=="heatmap":
  sheet=op.new_sheet("w",lname="Approved matrix source");sheet.from_df(frame)
  graph,upstream=cr._build_heatmap_graph(op,sheet,prep)
 else:graph,upstream=renderer._build_origin_graph(op,frame,output_paths(out,spec),prep,table_plan=table(spec,frame))
 apply_b(op,graph,spec,prep)
 report=inspect_native(op,graph,spec,out,source_sheet)
 output=output_paths(out,spec)
 assert op.save(str(output.result_opju)),"OPJU save failed"
 export_all(op,graph,output)
 write_new(out/"origin_render_report.json",{"status":"ORIGIN VERIFIED","readback":report,"upstream":upstream})

def reopen(op,out):
 req=read(out/"request.json");parent=Path(req["bundle"]);spec=read(parent/"figure_spec.json")
 require_hash(req["project"],req["project_sha256"]);assert op.open(req["project"])
 fresh=read(parent/"origin_render_report.json")["readback"];graph=op.find_graph(fresh["graph"])
 before=inspect_native(op,graph,spec,parent,fresh["source_sheet"])
 export_all(op,graph,output_paths(out,spec))
 write_new(out/"reopen_report.json",{"readback":before,"independent_process":True})
 edit=out/"native_edit";edit.mkdir()
 if spec["backend_route"]=="heatmap":
  m=op.find_sheet("m",before["matrix"]["worksheet"]);values=m.to_np2d();old=float(values[0,0]);values[0,0]=old+.7;m.from_np(values)
  change={"matrix":m.lt_range(False),"cell":[0,0],"before":old,"after":float(values[0,0])}
 else:
  binding=next(p["binding"] for p in before["plots"] if p["binding"]["role"]!="approved_error")
  sheet=op.find_sheet("w",binding["worksheet"]);values=sheet.to_list(binding["column"]);old=float(values[0]);values=[v+.35 if v is not None and np.isfinite(v) else v for v in values];sheet.from_list(binding["column"],values)
  change={"worksheet":sheet.lt_range(False),"column":binding["column"],"rows":"all_finite","delta":.35,"before_first":old,"after_first":values[0]}
 graph.activate();op.lt_exec("doc -uw;")
 assert op.save(str(output_paths(edit,spec).result_opju))
 export_all(op,graph,output_paths(edit,spec))
 write_new(edit/"edit_report.json",{"change":change,"scope":"Automated editability probe only, not approved scientific data","native_edit":True})

def batch(op,action,out):
 request=read(out/"batch_request.json");results=[]
 for path in request["bundles"]:
  target=Path(path);name=target.name
  print("START",action,name,flush=True)
  try:
   op.new()
   (render if action=="phase2c-render" else reopen)(op,target)
   results.append({"path":str(target),"status":"NATIVE_DONE"})
  except Exception as e:
   failure={"path":str(target),"status":"FAILED","error":str(e),"traceback":traceback.format_exc()}
   results.append(failure);write_new(target/"worker_failure.json",failure);traceback.print_exc()
   if action=="phase2c-render" and name=="heatmap":
    # Preserve the failed native graph for review; never mark it as a completed render.
    try:
     graph=op.find_graph();diagnostic=target/"diagnostic_native";diagnostic.mkdir()
     spec=read(target/"figure_spec.json");paths=output_paths(diagnostic,spec)
     assert op.save(str(paths.result_opju));export_all(op,graph,paths)
     write_new(diagnostic/"DIAGNOSTIC_ONLY.json",{"status":"PARTIAL","reason":str(e),"not_approved_for_production":True})
    except Exception as diagnostic_error:print("DIAGNOSTIC_EXPORT_FAILED",str(diagnostic_error),flush=True)
  print("END",name,results[-1]["status"],flush=True)
 write_new(out/"batch_report.json",{"action":action,"results":results,"owned_session":True})

