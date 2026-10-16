---
name: baihe-sci-design
description: 从有来源的科学内容设计机制图、构型图与多面板表达，交付FigureSpec、预览和施工合同，可设计到此为止。
---

# baihe-sci-design · 科学图设计


先理解研究问题和论证目标，再设计视觉表达。将事实、解释、假说、未知及工程建议分开，重要关系绑定来源跨度和证据级别；不按图面方便升级科学结论。

使用已配置的Scientific Visual Designer合同和冻结重放原语；宿主负责内容理解与设计，不把原语回放说成无人值守科学推理。不得执行旧批量render_all、改Holdout或重写冻结评分。

输出FigureSpec、ConstructionPlan、scientific_binding、IllustratorSceneGraph、设计预览、图注与未决项。核对关系方向、抑制/激活编码、假说虚线、对象层级及物理尺寸。非标准画布需从FigureSpec的物理宽度换算pt，并保留旧原语输出及修正来源。

0.2入口在预览前强制检查来源文件/哈希、主张、实体显式映射、关系方向、确定性、否定状态和视觉编码；编译后检查SceneGraph对应关系。矛盾只报错，不自动修正。输出相对引用的来源副本、跨合同一致性检查及元素处理清单。矢量生产需保留同目录三个科学sidecar；不能只传SceneGraph丢失来源。

入口为 `baihe-sci.cmd --module designer --spec <FigureSpec> --plan <ConstructionPlan> --binding <科学绑定>`。用户说“先设计/暂不画”时到设计交付为止。简单DIRECT、复杂HYBRID及可选IMAGE_GUIDED须有理由；没有当前费用与外传授权时不调用远程生成。

设计质量、施工质量、编辑性、科学正确性分开检查。所有必需科学要素要么在图中可见，要么在实际图注明示，要么记录经过同意的省略；内部计划包含不等于交付可见。作者接受待本人确认。

0.3可先`--preflight`核对科学骨架而不启动施工。需要时用evidence_map连接已有来源块、E证据和C主张；limits/contradicts/mixed保持待审，不自动采纳。布局可声明contains/disjoint/间隔/对齐/最终字号约束，程序只检查不自动重排；不要用这些检查替代视觉理解。相对引用的裁图、证据与区域地图随设计新交接复制。未知字可留omitted_pending_review草稿项，不能据此宣称正式图内容完整。接口例子见`文档/可选后端与任务操作.md`。
