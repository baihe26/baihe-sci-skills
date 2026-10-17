# Plot Semantics Contract v1

正式 quantitative production plot 先验证 `PLOT_SEMANTICS_CONTRACT.json`，再运行 renderer。科学目的和实验设计决定图型，不根据列数猜测。

必填：scientific_question、experimental_unit、identifiers（不存在的 ID 明确 null）、nesting_structure、point_semantics、statistical_n、x/y_variable、design、connection、summary、uncertainty、selected_archetype、source/plot_data/analysis 的 SHA256、plot_bindings、color_semantics。

分析清单必须声明 APPROVED_ANALYSIS_MANIFEST、批准来源与范围，并绑定原始观测和批准绘图数据。批准状态是来源声明，不代表软件自动获得了作者或统计专家批准；真实数据 pilot 必须另行确认。

语义入口：phase2c/semantics.py。JSON Schema 复用 jsonschema；实验单位只计身份，不计算统计量。validate_render_plan 阻止 renderer 把批准的散点改成连线、换点含义或增加未批准误差。recommend 只读科学目的与设计，不读表格列数。

每版输出保留 PLOT_DECISION_RECORD.json、原始层级观测、批准绘图数据、分析合同、FigureState/B style 哈希、OPJU、SVG/PDF/PNG、原生反读、独立重开、QA 与 manifest。

元数据不够：停止，询问处理/随机化发生在哪层、一个点对应什么、是否同一对象反复测量、谁批准了汇总与误差。禁止用 plausible 默认值补科学事实。


`independence_id_column` 必须与 declared experimental-unit id_column 一致，声明独立处理/制备/受试者的身份。软件检查声明和数据绑定的一致性；真实独立性仍需要实验设计证据。

误差量明确写 SD / SEM / CI / range / IQR / other / none；汇总明确写 mean / median / geometric_mean / model_estimate / other / none。native renderer 只消费批准列；当前测试覆盖不等于所有类型已验证。非对称区间、置信带和 mixed-model 可视化详见 registry，未完成的能力不能静默替换成 sample SD。

native box/violin/histogram 的 quartile/KDE/bin display geometry 必须由分析清单明确授权；不进行 inferential fit/test、P value、异常值删除或技术重复聚合。KDE bandwidth 与 native box whisker/quartile 设置保留于 OPJU；未逐项数值校核时不得声称模型/分位数算法等价。

`PLOT_DECISION_RECORD.executed.json` 是执行时从冻结合同生成的 12 项记录，保留原始 decision record 以便追踪。所有角色绑定同时固定 y/x/error 列，防止只保持 Y 值而偷偷换 X、误差列或 point meaning。
