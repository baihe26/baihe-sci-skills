# Plot Decision Rules v2

更新：2026-10-08；只调整候选与偏好层。Phase2A PASSED、Phase2C.1 closure、B style 与既有 native acceptance 保留。

> Bar charts are a first-class scientific archetype when the scientific structure and reading task support categorical summary comparison. For small-n continuous data, bar charts should normally retain visible independent-unit observations. Bar use is not penalized merely for being traditional, and raw-point-only plots are not automatically considered superior.

| 问题与设计 | 一级候选 / 科学路由 | 必须核查 |
|---|---|---|
| 独立 categorical groups + 连续 endpoint + small/moderate biological n | **bar_raw 与 grouped_raw_summary 同级比较** | A：bar＋独立点＋approved error；B：raw＋approved summary/error；没有点图优越性默认 |
| 同一独立对象两条件 | paired_dot_slope | 精确 pair ID；缺一端停止，不按行号补配对 |
| 连续/有序 X 上的 group summary | longitudinal_summary | repeated / independent-by-X 明确区分；后者不能画 individual traces；不因导师先验丢掉时间关系 |
| 两个连续变量 | scatter_correlation | scatter only；批准模型才画 fit/CI，不因先验改 bar |
| 连续采集信号 | multi_xy_curve | real numerical X；dense spectrum line dominant；采样数不是独立 n |
| median/IQR 或分布形状问题 | box_raw / violin_raw | 分布适用性与 independent n 已批准；n=3–5 不凭空画 KDE |
| 真正分布问题 | histogram_ecdf | approved bins/ECDF；subsamples ≠ biological n |
| feature × sample / matrix | heatmap | continuous colormap；group palette 仅作组身份注释 |
| calibration / dose response | dose_response_calibration | 原始 points；批准模型/参数/范围/排除/CI 才加曲线 |

## 终点比较的选择

候选列表是集合，不是质量排名；不得无理由淘汰 bar。

- 快速比较组总体高低（`reading_task=compare_group_levels`）：可优先 bar＋raw。
- 强调组内变异和个体分布（`reading_task=within_group_variation`）：可优先 raw＋summary。
- 再检查组数、独立 n、数据密度、manuscript composition、advisor prior。未记录的阅读任务/密度写 `not_recorded`；不要从列数猜。
- 科学上都合适且无上级约束冲突时，既有 advisor prior 可建议 bar；建议不修改已批准 selected_archetype，不执行 renderer。
- `explicit_summary_bar` 仍兼容；不再要求用户说出“传统柱状图”才纳入 bar。Ordinal 仍需专门的科学理由，不能自动当 continuous；continuous irregular X 使用真实数值距离。

优先级：scientific validity → experimental design/statistical semantics → publisher constraints → manuscript consistency → advisor prior → local aesthetic preference。导师先验仅在科学上可行的方案之间作 tie-breaker。

## Bar＋raw 的硬边界

bar 表示 analysis owner 已批准的 summary；error quantity 来自 approved SD / SEM / CI / range / IQR / other（若批准为 none 则不添误差）。renderer 不决定、计算或替换 summary/error，不做 outlier removal、aggregation、fit 或 P value。

small-n continuous data 保留真正 independent units 的 prominent points。3 animals/group × 50 cells/animal：主点是 **3 个已批准 animal summaries**，inferential n=3；cell/field 仅按既有 nested display contract 作 secondary layer。不能把 150 cells 变成 biological n。

未知 purpose 停止；paired/repeated 不落入 independent-group 默认。合同/source/approved analysis/X-Y-error bindings/FigureState owner/display override 原门禁全部保留。既有 sample SD 不是未来全局唯一 error。

## PLOT_DECISION_RECORD

保留原 12 项；新增候选集、reading task、组数/独立 n/密度记录及：

| 字段 | 值与含义 |
|---|---|
| `BAR_CANDIDACY` | `ELIGIBLE`：科学可用，解释 bar＋raw；`NOT_PREFERRED`：科学可用但当前阅读任务优先 raw＋summary；`NOT_SCIENTIFICALLY_APPROPRIATE`：purpose/design 不属于适用范围 |
| `ADVISOR_PRIOR_EFFECT` | `NONE`：不适用；`SUPPORTS_BAR` / `SUPPORTS_RAW_SUMMARY`：必须有可定位证据；`INCONCLUSIVE`：缺少适用证据，不猜 |
| `ADVISOR_PRIOR_EVIDENCE` | corpus/card ID、DOI、figure/panel/page、来源 hash、权重与记录路径 |

当前既有证据只支持 scoped `SUPPORTS_BAR`，不制造支持 raw 的导师证据。`decide(contract, reading_task=...)` 输出建议，**不自动变更批准图型**。正式使用前仍完成原 validate 与 analysis approval；候选资格不是新 native acceptance。

[导师偏好证据与边界](ADVISOR_AWARE_PLOT_PREFERENCE.md)。继承 STYLE_V0_1_SELECTED：Arial、typography、stable group colors/markers、error/legend/annotation grammar、anti-AI；不重新校准，不重分配颜色。

分布 n 阈值仅为既有 synthetic 安全门槛；box/violin capability 状态不变。stacked/composition、cyclic 与 specialized families 的既有注册及批准要求保持；不由 GUI 菜单推定 production validated。本轮无新 archetype、Origin runtime 或 REAL-DATA PILOT。
