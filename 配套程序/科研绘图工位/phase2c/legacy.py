"""Semantic bridge for immutable, previously approved FigA/FigB synthetic fixtures."""
from pathlib import Path
import json,csv
from figure_system.common import ROOT,read,sha,require_hash
from .semantics import validate,decide
def build():
 base=ROOT/"phase2c/legacy_contracts";base.mkdir(exist_ok=True)
 for fig in ("FigA","FigB"):
  d=base/fig
  if d.exists():continue
  d.mkdir();old=read(ROOT/"fixtures/contracts"/(fig+".json"))
  raw=ROOT/"fixtures/source"/old["source"];summary=ROOT/"fixtures/source"/old["summary"]
  require_hash(raw,old["source_sha256"]);require_hash(summary,old["summary_sha256"])
  rows=list(csv.DictReader(raw.open(encoding="utf-8-sig",newline="")))
  xkey="condition" if fig=="FigA" else "time"
  for row in rows:row["x"]=row[xkey]
  with (d/"observations.csv").open("w",encoding="utf-8",newline="") as f:
   writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
  (d/"legacy_plot_data.csv").write_bytes(summary.read_bytes())
  strata={row["group"]+"|"+row["x"]:8 for row in rows}
  n={"STATISTICAL_N_IS":"independent_synthetic_unit","stratum_columns":["group","x"],"by_stratum":strata}
  c={"schema_version":1,"scientific_question":old["core_claim"],"experimental_unit":{"type":"independent_synthetic_unit","id_column":"unit_id","independence_id_column":"unit_id",
   "definition":"Original approved synthetic unit ID. FigB reuses the same unit IDs across time, descriptively."},
   "identifiers":{"biological_replicate_id":None,"technical_replicate_id":None,"subject_id":"unit_id","sample_id":"unit_id","batch_id":None},
   "nesting_structure":[],"point_semantics":{"ONE_POINT_IS":"one independent synthetic unit" if fig=="FigA" else "one approved time/group mean",
   "primary_level":"experimental_unit" if fig=="FigA" else "group_summary","subsample_display":False},"statistical_n":n,
   "x_variable":{"type":"categorical" if fig=="FigA" else "continuous","spacing":"explicit_category" if fig=="FigA" else "real_numeric"},
   "y_variable":{"type":"continuous","units":"a.u."},"design":{"paired":False,"repeated":fig=="FigB","independent_by_x":False,
   "pair_id_column":"unit_id" if fig=="FigB" else None},"connection":{"mode":"none" if fig=="FigA" else "group_summary"},
   "summary":{"type":"mean"},"uncertainty":{"type":"SD","quantity_column_suffix":"std"},
   "selected_archetype":"grouped_raw_summary" if fig=="FigA" else "longitudinal_summary","purpose":"comparison" if fig=="FigA" else "ordered_time_summary",
   "source":{"path":"observations.csv","sha256":sha(d/"observations.csv")},"plot_data":{"path":"legacy_plot_data.csv","sha256":sha(d/"legacy_plot_data.csv")},
   "plot_bindings":[{"column":"value","role":"unit","unit_ids":[r["unit_id"] for r in rows if r["group"]==g and r["x"]==str(x)]}
     for g in sorted({r["group"] for r in rows}) for x in old["x_order"]] if fig=="FigA" else [{"column":"mean","role":"group_summary","unit_ids":[]}],
   "color_semantics":{"kind":"categorical"},"raw_prominent":True,
   "analysis":{"path":"legacy_analysis_bridge.json","sha256":""},
   "original_analysis_sha256":old["analysis_sha256"],"original_source_sha256":old["source_sha256"]}
  a={"schema_version":1,"status":"APPROVED_ANALYSIS_MANIFEST","approved_by":"USER_APPROVED_EXISTING_SYNTHETIC_BASELINE",
   "approval_scope":"Preserve original FigA/FigB mean and sample SD; no statistical recomputation or real inference",
   "source_sha256":c["source"]["sha256"],"plot_data_sha256":c["plot_data"]["sha256"],
   "statistical_n":n,"summary":c["summary"],"uncertainty":c["uncertainty"],"approved_plot_bindings":c["plot_bindings"],
   "original_analysis_sha256":old["analysis_sha256"]}
  (d/"legacy_analysis_bridge.json").write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding="utf-8")
  c["analysis"]["sha256"]=sha(d/"legacy_analysis_bridge.json")
  (d/"PLOT_SEMANTICS_CONTRACT.json").write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding="utf-8")
  (d/"PLOT_DECISION_RECORD.json").write_text(json.dumps(decide(c),ensure_ascii=False,indent=2),encoding="utf-8")
  validate(c,d)
def gate(fig):
 d=ROOT/"phase2c/legacy_contracts"/fig
 validate(read(d/"PLOT_SEMANTICS_CONTRACT.json"),d)
 return d
if __name__=="__main__":build();print("LEGACY_CONTRACTS_READY")

