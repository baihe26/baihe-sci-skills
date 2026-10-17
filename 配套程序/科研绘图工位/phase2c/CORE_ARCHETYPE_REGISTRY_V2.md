# Core archetype registry V2

OriginPro 2026 SR0（10.3.0.180），B style 保留。PRODUCTION_VALIDATED 只覆盖声明的 synthetic 变体；人工审核待完成。旧 registry 不覆盖，V2 为本轮权威增量。

|Family|状态|已验证范围|证据|
|---|---|---|---|
|grouped_raw_summary|PRODUCTION_VALIDATED|independent units per categorical group; approved mean/sample SD|[FigA](../artifacts/bundles/phase2c_legacy_FigA_20261007)|
|longitudinal_summary|PRODUCTION_VALIDATED|Legacy summary retained; repeated n=8 animals/group and independent-by-time n=8/time/group; positive synthetic schedule linear/log10/categorical modes|[FigB](../artifacts/bundles/phase2c_legacy_FigB_20261007)|
|paired_dot_slope|PRODUCTION_VALIDATED|8 exact paired animals; each line joins the same unit|[paired_dot_slope](../phase2c/runs/20261007_204928/paired_dot_slope)|
|scatter_correlation|PRODUCTION_VALIDATED|12 independent animals/group; scatter only; no automatic fit|[scatter_correlation](../phase2c/runs/20261007_194020/scatter_correlation)|
|multi_xy_curve|PRODUCTION_VALIDATED|3 batches, 301 acquisition samples/curve; line only; real numerical X|[multi_xy_curve](../phase2c/runs/20261007_194020/multi_xy_curve)|
|box_raw|PARTIAL|24 independent units/group; native box + raw overlay; blocked|[box_raw](../phase2c/runs/20261007_194020/box_raw)|
|violin_raw|PARTIAL|40 independent units/group; approved native KDE display; blocked|[violin_raw](../phase2c/runs/20261007_194020/violin_raw)|
|bar_raw|PRODUCTION_VALIDATED|n=4 independent animals/group; approved mean/sample SD + translucent native bars + prominent opaque raw points; native/SVG/PNG geometry|[bar_raw](../phase2c/runs/closure_20261007_225734/bar_raw)|
|histogram_ecdf|PRODUCTION_VALIDATED|60 independent particles; explicit native bins and strict horizontal-step ECDF|[histogram](../phase2c/runs/20261007_194020/histogram)|
|heatmap|PRODUCTION_VALIDATED|6x6 unnormalized matrix, sequential Viridis, source IDs retained with compact display labels; native Color Scale title/ticks/cells Arial 7pt|[heatmap](../phase2c/runs/closure_20261007_235708/heatmap_compact_labels)|
|dose_response_calibration|PRODUCTION_VALIDATED|7 measured samples + approved known-parameter 4PL reference; linear X|[calibration_linear](../phase2c/runs/20261007_200635/calibration_linear)|

box_raw / violin_raw 保持 PARTIAL：native 创建/保存/重开/编辑已有证据，但 stable identity、legend、collision 与 quartile/whisker/outlier 或 KDE/bandwidth 等价性未闭环，不进入 production。

longitudinal 新增变体仅覆盖冻结 schedule；log 已验证的是该 synthetic longitudinal，不能外推到 dose-response log 或 log spectrum。SEM/CI/band/model-fitting、diverging heatmap、大规模矩阵、secondary cell-level overlay 仍按原记录保留未验证状态。specialized registry 未改变。

旧 7 类未重新渲染，复用原验收并核验冻结 artifacts、原 fixture 和 B style 哈希；见 [验收 V2](PHASE2C_ACCEPTANCE_V2.md)。
