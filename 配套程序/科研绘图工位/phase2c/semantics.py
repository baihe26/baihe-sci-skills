"""Experimental-unit and plot-choice gates. Validation, never statistical analysis."""
from pathlib import Path
import csv, json
from jsonschema import Draft202012Validator
from figure_system.common import sha, require_hash

class SemanticsError(ValueError): pass
CORE = ("grouped_raw_summary","longitudinal_summary","paired_dot_slope","scatter_correlation",
        "multi_xy_curve","box_raw","violin_raw","bar_raw","histogram_ecdf","heatmap","dose_response_calibration")
IDS = ("biological_replicate_id","technical_replicate_id","subject_id","sample_id","batch_id")
SCHEMA = {
 "$schema":"https://json-schema.org/draft/2020-12/schema","type":"object",
 "required":["schema_version","scientific_question","experimental_unit","identifiers","nesting_structure",
             "point_semantics","statistical_n","x_variable","y_variable","design","connection",
             "summary","uncertainty","selected_archetype","purpose","analysis","source","plot_data",
             "plot_bindings","color_semantics"],
 "properties":{
  "schema_version":{"const":1},
  "scientific_question":{"type":"string","minLength":8},
  "experimental_unit":{"type":"object","required":["type","id_column","definition"],
   "properties":{"type":{"type":"string","minLength":2},"id_column":{"type":"string","minLength":1},
                 "definition":{"type":"string","minLength":8}}},
  "identifiers":{"type":"object","required":list(IDS)},
  "nesting_structure":{"type":"array"},
  "point_semantics":{"type":"object","required":["ONE_POINT_IS","primary_level","subsample_display"]},
  "statistical_n":{"type":"object","required":["STATISTICAL_N_IS","stratum_columns","by_stratum"]},
  "x_variable":{"type":"object","required":["type","spacing"],"properties":{"type":{"enum":["categorical","ordinal","continuous"]}}},
  "y_variable":{"type":"object","required":["type","units"]},
  "design":{"type":"object","required":["paired","repeated","independent_by_x","pair_id_column"]},
  "connection":{"type":"object","required":["mode"],"properties":{"mode":{"enum":["none","paired","individual_trajectory","group_summary","continuous_measurement","approved_model","ecdf"]}}},
  "summary":{"type":"object","required":["type"],"properties":{"type":{"enum":["none","mean","median","geometric_mean","model_estimate","other"]}}},
  "uncertainty":{"type":"object","required":["type"],"properties":{"type":{"enum":["none","SD","SEM","CI","range","IQR","other"]}}},
  "selected_archetype":{"enum":list(CORE)},
  "analysis":{"type":"object","required":["path","sha256"]},
  "source":{"type":"object","required":["path","sha256"]},
  "plot_data":{"type":"object","required":["path","sha256"]},
  "plot_bindings":{"type":"array","minItems":1},
  "color_semantics":{"type":"object","required":["kind"],"properties":{"kind":{"enum":["categorical","sequential","diverging","cyclic"]}}}
 }}
def _require(ok, message):
 if not ok: raise SemanticsError(message)
def read_json(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def stratum(row, columns): return "|".join(row[c] for c in columns)
def validate(contract, base):
 Draft202012Validator(SCHEMA).validate(contract)
 base=Path(base)
 for field in ("analysis","source","plot_data"):
  p=(base/contract[field]["path"]).resolve()
  _require(p.is_relative_to(base.resolve()),"Contract path escapes its bundle")
  require_hash(p,contract[field]["sha256"])
 a=read_json(base/contract["analysis"]["path"])
 _require(a.get("status")=="APPROVED_ANALYSIS_MANIFEST","Analysis approval missing")
 _require(a.get("approved_by") and a.get("approval_scope"),"Approval identity/scope missing")
 _require(a.get("source_sha256")==contract["source"]["sha256"] and a.get("plot_data_sha256")==contract["plot_data"]["sha256"],"Analysis/source/plot binding mismatch")
 _require(a.get("summary")==contract["summary"] and a.get("uncertainty")==contract["uncertainty"],"Statistical semantics differ from approved analysis")
 rows=list(csv.DictReader((base/contract["source"]["path"]).open(encoding="utf-8-sig",newline="")))
 _require(bool(rows),"Empty observations")
 unit=contract["experimental_unit"]; idcol=unit["id_column"]
 _require(unit.get("independence_id_column")==idcol,"Experimental unit must match the declared independent treatment/preparation/subject identity")
 _require(all(r.get(idcol) for r in rows),"Missing experimental-unit IDs")
 for name,col in contract["identifiers"].items():
  _require(col is None or all(col in r for r in rows),"Missing declared identifier column: "+name)
 units={}
 for r in rows: units.setdefault(stratum(r,contract["statistical_n"]["stratum_columns"]),set()).add(r[idcol])
 counts={k:len(v) for k,v in units.items()}
 _require(counts==contract["statistical_n"]["by_stratum"],"Inferential n must count experimental units, never rows/cells/images")
 _require(contract["statistical_n"]["STATISTICAL_N_IS"]==unit["type"],"Statistical-n unit differs from experimental unit")
 _require(a.get("statistical_n")==contract["statistical_n"],"Approved n differs from contract")
 from graphlib import TopologicalSorter,CycleError
 tree={}
 for edge in contract["nesting_structure"]: tree.setdefault(edge["child"],set()).add(edge["parent"])
 try: tuple(TopologicalSorter(tree).static_order())
 except CycleError: raise SemanticsError("Nesting hierarchy contains a cycle")
 for edge in contract["nesting_structure"]:
  _require(set(edge)=={"parent","child"} and edge["parent"]!=edge["child"],"Invalid nesting edge")
  parents={}
  for r in rows:
   _require(r.get(edge["parent"]) and r.get(edge["child"]),"Missing hierarchy identity")
   parents.setdefault(r[edge["child"]],set()).add(r[edge["parent"]])
  _require(all(len(v)==1 for v in parents.values()),"A nested child belongs to multiple parents")
 mode=contract["connection"]["mode"]; d=contract["design"]; x=contract["x_variable"]["type"]; kind=contract["selected_archetype"]
 _require(not (d["repeated"] and d["independent_by_x"]),"Repeated and independent-by-X conflict")
 if mode in ("paired","individual_trajectory"):
  _require(d["paired"] or d["repeated"],"Connections need pairing or repeated-measures design")
  _require(d["pair_id_column"]==idcol,"Pair ID must identify the independent unit")
  coords=contract.get("connection_keys",[])
  _require(bool(coords),"Exact paired/trajectory coordinates must be declared")
  for uid in {r[idcol] for r in rows}:
   found=[r[contract["x_variable"].get("column","x")] for r in rows if r[idcol]==uid]
   _require(len(found)==len(set(found)) and set(found)==set(map(str,coords)),"Missing/duplicate pair: "+uid)
 if contract.get("individual_traces"): _require(d["repeated"],"Individual traces cannot connect independently sampled time cohorts")
 if mode=="group_summary":
  _require(x in ("continuous","ordinal"),"Nominal categorical groups cannot imply a trend")
  _require(d["repeated"] or d["independent_by_x"],"Summary trend needs sampling design")
 if mode=="continuous_measurement":
  _require(x=="continuous" and contract["purpose"]=="continuous_signal","Continuous curves require continuous measurement semantics")
 if x=="continuous":
  _require(contract["x_variable"]["spacing"]=="real_numeric","Irregular numerical X spacing cannot be replaced by equal categories")
 if x=="ordinal" and mode!="none": _require(contract.get("ordinal_connection_reason"),"Ordinal connection needs a scientific justification")
 if kind=="paired_dot_slope": _require(mode=="paired" and d["paired"],"Paired archetype needs exact pair identities")
 if kind=="scatter_correlation":
  _require(x=="continuous" and contract["y_variable"]["type"]=="continuous","Scatter needs two continuous variables")
  _require(mode in ("none","approved_model"),"Scatter must not join unrelated observations")
 if mode=="approved_model":
  _require(a.get("models"),"Fit curve requires an approved model, parameters and fitting range")
  for model in a["models"]:
   _require(all(k in model for k in ("model","parameters","fitting_range","excluded_points","CI")),"Incomplete approved model")
 if kind=="multi_xy_curve":
  _require(mode=="continuous_measurement","Spectrum/curve semantics required")
  if contract.get("dense_sampling"): _require(not contract.get("markers",False),"Dense spectra must not add markers at every acquisition sample")
 if kind in ("box_raw","violin_raw"):
  adequate=a.get("distribution_adequacy",{})
  _require(adequate.get("approved") and adequate.get("reason"),"Distribution/density adequacy must be explicitly approved")
  _require(min(counts.values())>=adequate.get("min_independent_n",10**9),"Independent n too small for approved distribution rule")
 if kind in ("grouped_raw_summary","bar_raw") and min(counts.values())<=5:
  _require(contract.get("raw_prominent"),"Small independent n needs prominent raw unit values")
 primary=contract["point_semantics"]["primary_level"]
 if primary not in ("experimental_unit","group_summary","group_distribution","matrix_cell","acquisition_coordinate"):
  _require(contract["point_semantics"]["subsample_display"] and a.get("hierarchical_model"),"Subsample-primary display requires explicit hierarchy/model; cells are not biological n")
 _require(a.get("approved_plot_bindings")==contract["plot_bindings"],"Point meanings differ from approved analysis bindings")
 for b in contract["plot_bindings"]:
  _require(b.get("role") in ("unit","unit_summary","group_summary","continuous_samples","approved_fit","approved_distribution","matrix","subsamples"),"Unknown point binding role")
  if b["role"] in ("unit","unit_summary"):
   ids=b.get("unit_ids",[])
   _require(ids and len(ids)==len(set(ids)),"Primary points cannot duplicate an independent unit within a plotted stratum")
   _require(set(ids)<=set().union(*units.values()),"Point references unknown independent unit")
  if b["role"]=="approved_fit": _require(mode=="approved_model","Unapproved fitted series")
  if b["role"]=="subsamples": _require(contract["point_semantics"]["subsample_display"],"Hidden subsample role")
 if kind=="heatmap":
  _require(contract["color_semantics"]["kind"]!="categorical","Heatmap magnitude scale is not the stable group palette")
 if contract["color_semantics"]["kind"]=="diverging":
  _require("center" in contract["color_semantics"],"Diverging scale needs a meaningful center")
 _require(contract["selected_archetype"] in recommend(contract),"Archetype conflicts with scientific purpose/design")
 return {"pass":True,"unit_counts":counts,"row_count":len(rows),"experimental_unit":unit["type"],"selected_archetype":kind}

def decide(contract, reading_task=None):
 """A concise record from approved semantics; never infers semantics from table shape."""
 choices={
 "grouped_raw_summary":("Independent categorical comparisons with raw unit values","Bar+raw is an equally valid candidate; compare the reading task. Lines need a trajectory."),
 "longitudinal_summary":("Ordered X with explicitly repeated or independent-by-X sampling","Individual traces are inappropriate for independent units at different X."),
 "paired_dot_slope":("Connections identify the same experimental unit across paired conditions","Independent scatter would discard pairing."),
 "scatter_correlation":("Two continuous variables measured on identified independent units","Fit lines require an approved model; unrelated points must not be joined."),
 "multi_xy_curve":("Continuous acquisition signal on real numerical X","Dense markers would imply scientifically meaningful discrete samples."),
 "box_raw":("Approved median/quartile distribution with independent unit observations","For small n, use raw points; density is not required."),
 "violin_raw":("Approved density-shape question with sufficient independent units","Many nested cells alone do not provide independent biological n."),
 "bar_raw":("Approved categorical summary bar with visible independent unit observations","Raw+summary is an equally valid candidate; compare the reading task. Small-n bars retain unit variation."),
 "histogram_ecdf":("Approved distribution question and independent-unit count","Counts of pores/cells are not automatically biological replicate counts."),
 "heatmap":("Approved feature-by-sample matrix and continuous magnitude scale","Categorical group colors are annotations, not a continuous color scale."),
 "dose_response_calibration":("Measured points and an externally approved mathematical model, if present","Joining points is not fitting or calibration.") }
 reason,alternatives=choices[contract["selected_archetype"]]
 return {"scientific_question":contract["scientific_question"],"experimental_unit":contract["experimental_unit"],
 "statistical_n":contract["statistical_n"],"nested_subsamples":contract["nesting_structure"],
 "x_variable":contract["x_variable"],"y_variable":contract["y_variable"],"paired_repeated":contract["design"],
 "approved_summary":contract["summary"],"approved_uncertainty":contract["uncertainty"],
 "selected_plot_archetype":contract["selected_archetype"],"why":reason,"alternatives_not_selected":alternatives,
 **plot_preference(contract, reading_task)}


def validate_render_plan(c,spec,base):
 """Keep native primitives consistent with the signed semantic bindings."""
 import pandas as pd
 _require(spec["plot_kind"]==c["selected_archetype"],"Native archetype differs from semantic decision")
 expected=[{"column":s["y"],"x_column":s.get("x"),"error_column":s.get("error"),"role":s.get("role","unit"),"unit_ids":s.get("unit_ids",[])} for s in spec["series"]]
 _require(expected==c["plot_bindings"],"Native series would change approved point meanings")
 if spec.get("native_bar_fill_transparency_percent"):
  analysis=read_json(Path(base)/c["analysis"]["path"])
  _require(analysis.get("approved_bar_display")==c.get("approved_bar_display") and analysis["approved_bar_display"]["fill_transparency_percent"]==spec["native_bar_fill_transparency_percent"],"Bar display override must be explicitly approved")
 frame=pd.read_csv(Path(base)/c["plot_data"]["path"],float_precision="round_trip")
 for s in spec["series"]:
  _require(s["y"] in frame and (not s.get("x") or s["x"] in frame),"Missing approved plot column")
  mode=c["connection"]["mode"]
  if mode=="none":
   _require(s["plot_type"] in ("s","c","box"),"Native primitive would join unrelated observations")
  if mode=="continuous_measurement" and c.get("dense_sampling"):
   _require(s["plot_type"]=="l","Dense acquisition curves must remain line-only")
  if mode=="ecdf":_require(s["plot_type"]=="l","ECDF uses approved probability values and native horizontal steps")
  if s.get("individual_trace"):
   _require(c["design"]["repeated"],"Unrelated units cannot be drawn as individual trajectories")
  if s.get("error"):
   _require(c["uncertainty"]["type"]!="none" and s["error"] in frame,"Unapproved uncertainty column")
  if s["role"] in ("unit","unit_summary") and not c["design"]["paired"] and not c["design"]["repeated"]:
   _require(len(frame[s["y"]].dropna())==len(s["unit_ids"]),"Raw primary point count differs from experimental-unit identity count")
 _require(not spec.get("x_scale")=="log10" or all((frame[s["x"]].dropna()>0).all() for s in spec["series"] if s.get("x")),"Log X needs positive approved coordinates")
 return True

def recommend(c):
 """Permitted families from question/design. Column count is never consulted."""
 purpose=c["purpose"];d=c["design"]
 if purpose=="continuous_signal": return ["multi_xy_curve"]
 if purpose=="feature_by_sample_matrix": return ["heatmap"]
 if purpose=="two_variable_relationship": return ["scatter_correlation"]
 if purpose=="within_unit_change" and d["paired"]: return ["paired_dot_slope"]
 if purpose=="ordered_time_summary": return ["longitudinal_summary"]
 if purpose=="approved_calibration_model": return ["dose_response_calibration"]
 if purpose=="distribution": return ["histogram_ecdf"]
 if purpose=="distribution_shape": return ["box_raw","violin_raw"]
 if purpose in ("comparison","explicit_summary_bar"):
  _require(c["x_variable"]["type"] in ("categorical","ordinal"),"Independent group comparison needs categorical/ordinal design; continuous X needs a declared relationship purpose")
  _require(not d["paired"] and not d["repeated"],"Paired/repeated design must preserve unit identity; independent-group defaults are forbidden")
  if c["y_variable"]["type"]=="continuous" and c["summary"]["type"]!="none" and (purpose=="explicit_summary_bar" or c["x_variable"]["type"]=="categorical"):
   return ["bar_raw","grouped_raw_summary"]  # Candidate set, not a quality ranking.
  return ["grouped_raw_summary"]
 raise SemanticsError("Unknown scientific purpose; clarify the question instead of selecting a chart default")


def _advisor_bar_evidence():
 """Reuse verified frozen cards; no new corpus, web query or preference scores."""
 from figure_system.common import ROOT
 folder=ROOT/"phase2b/CX_STYLE_V0_1_FREEZE_20261007"
 corpus_path=folder/"ADVISOR_CORPUS.json";registry_path=folder/"REFERENCE_PANEL_REGISTRY.json"
 if not corpus_path.is_file() or not registry_path.is_file(): return []
 papers={p["paper_id"]:p for p in read_json(corpus_path)["papers"]}
 cards={p["id"]:p for p in read_json(registry_path)["candidates"]}
 evidence=[]
 for card_id,paper_id in (("G09","B1"),("G10","B2"),("G11","B2")):
  card=cards.get(card_id);paper=papers.get(paper_id)
  if not card or not paper: continue
  if not (card["paper_id"]==paper_id and card["doi"]==paper["doi"] and card["provenance"].get("actually_viewed") and card["plot_archetype"].startswith("bar + raw")): continue
  evidence.append({"card_id":card_id,"paper_id":paper_id,"doi":paper["doi"],
   "figure":card["figure"],"panel":card["panel"],"pdf_page_1_based":card["pdf_page_1_based"],
   "role":paper["role"],"weight":"HIGHEST_ADVISOR_PRIOR" if paper_id=="B1" else card["selection"],
   "source_pdf_sha256":card["provenance"]["pdf_sha256"],
   "corpus_path":corpus_path.relative_to(ROOT).as_posix(),"corpus_sha256":sha(corpus_path),
   "registry_path":registry_path.relative_to(ROOT).as_posix(),"registry_sha256":sha(registry_path)})
 return evidence


def plot_preference(c, reading_task=None):
 """Advisory tie-breaker only. Never changes the approved selection or statistics."""
 choices=recommend(c)
 task=reading_task if reading_task is not None else c.get("reading_task","not_recorded")
 eligible="bar_raw" in choices
 categorical_endpoint=eligible and c["x_variable"]["type"]=="categorical" and c["connection"]["mode"]=="none"
 evidence=_advisor_bar_evidence() if categorical_endpoint else []
 effect=("SUPPORTS_BAR" if evidence else "INCONCLUSIVE") if categorical_endpoint else "NONE"
 suggested=None
 if not eligible:
  candidacy="NOT_SCIENTIFICALLY_APPROPRIATE"
  reason="This purpose/design is outside categorical summary-bar comparison. Preserve the scientific encoding."
 elif task=="within_group_variation":
  candidacy="NOT_PREFERRED";suggested="grouped_raw_summary"
  reason="Bar+raw is scientifically eligible; the stated reading task prioritizes individual variation."
 else:
  candidacy="ELIGIBLE"
  reason="Independent categorical summary comparison; bar reads the approved quantity and retains independent-unit points."
  if task=="compare_group_levels" or (task=="not_recorded" and effect=="SUPPORTS_BAR"):
   suggested="bar_raw"
 return {"plot_candidates":choices,"candidate_order_is_ranking":False,"reading_task":task,
  "BAR_CANDIDACY":candidacy,"BAR_CANDIDACY_REASON":reason,
  "ADVISOR_PRIOR_EFFECT":effect,"ADVISOR_PRIOR_EVIDENCE":evidence,
  "preference_suggestion":suggested,
  "preference_scope":"Advice among scientifically eligible candidates; publisher constraints and manuscript consistency take precedence. No automatic reselection.",
  "layout_considerations":{"group_count":len(c["statistical_n"]["by_stratum"]) if categorical_endpoint and c["statistical_n"]["stratum_columns"]==["group"] else "not_recorded","independent_n":c["statistical_n"]["by_stratum"],"data_density":"not_recorded; inspect approved display before final selection"}}


def validate_style_owner(c,spec):
 from figure_system.state import load_state
 from figure_system.common import ROOT,sha
 state=load_state("style_v0_1_selected")
 _require(spec["style_version"]==state["style_version"] and spec["style_sha256"]==sha(ROOT/"fixtures/styles/style_v0_1_selected.json"),"B style ownership mismatch")
 _require(spec["manuscript_id"]==state["manuscript_id"],"Manuscript owner differs")
 _require(c.get("figurestate_owner")=={"style_version":state["style_version"],"style_sha256":sha(ROOT/"fixtures/styles/style_v0_1_selected.json"),"manuscript_id":state["manuscript_id"]},"Semantic contract must retain the same FigureState manuscript/style owner")
 for gid,g in spec["groups"].items():_require(g==state["groups"][gid],"Categorical group identity differs from FigureState")
 expected=dict(state["tokens"]);expected.update(c.get("approved_geometry_override",{}))
 _require(all(k in ("width_mm","height_mm","layer_left_percent","layer_top_percent","layer_width_percent","layer_height_percent") for k in c.get("approved_geometry_override",{})),"Style override would change B grammar")
 _require(spec["tokens"]==expected,"Unapproved style tokens in renderer")
 return True

