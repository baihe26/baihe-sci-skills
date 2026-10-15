# baihe-sci skills

从科研数据图、科学图设计，到可编辑矢量与科研汇报的本地技能系列。

**当前版本：0.1.0，依赖外部本地引擎的技能与薄适配层。** 本仓库包含可执行协调代码；不包含Origin、Illustrator、PowerPoint、私有底层引擎及其许可。克隆后可读取技能、运行帮助和依赖诊断；原生生产需按说明配置兼容引擎。

|技能|用途|
|---|---|
|[`baihe-sci`](skills/baihe-sci/SKILL.md)|总入口，选择单模块或跨模块链路|
|[`baihe-sci-plot`](skills/baihe-sci-plot/SKILL.md)|科研数据语义、可编辑数据图、论文/汇报显示副本|
|[`baihe-sci-design`](skills/baihe-sci-design/SKILL.md)|科学内容理解、构型与机制设计、FigureSpec与施工交付|
|[`baihe-sci-vector`](skills/baihe-sci-vector/SKILL.md)|忠实重建或按批准设计生产，AI/PPT原生对象与局部编辑|
|[`baihe-sci-slides`](skills/baihe-sci-slides/SKILL.md)|科研汇报、原生文字、媒体完整性、稳定引用和局部修订|

## 开始使用

1. 阅读[安装与配置](文档/安装与配置.md)。Python 3.11+可运行帮助和诊断；原生软件链路在Windows环境验证。
2. 复制 `baihe-sci.example.json` 为 `baihe-sci.local.json`，填写自己的引擎与Python路径。本机配置被Git忽略。不要提交密钥或研究路径。
3. 运行 `baihe-sci.cmd --doctor`；或 `python 工作台/源码/workbench.py --doctor`。诊断只检查依赖文件，不自动安装或启动软件。
4. 在Codex里说：“使用 $baihe-sci，只设计这张图，先不生产。”也可以只调用一个子技能。

技能目录可以在本地项目中直接读取；若按Codex的技能安装方式逐个安装，仍须保留本仓库并让宿主通过 `BAIHE_SCI_HOME` 或明确路径定位共享工作台。不要只复制SKILL.md后宣称原生引擎已安装。

## 示例与验证

- [合成设计示例](示例/简单科学关系)：A向B的给定连接与B向A的假说分开；无真实科研数据。
- [能力与验证范围](文档/能力与验证范围.md)：历史原生结果、本次发布验证、未验证项分开。
- [复用与依赖](文档/复用与依赖.md)：来源、版本、外部依赖和未再分发内容。
- [发布检查](发布检查.json)：本次打包、隐私扫描与自动检查范围。

本仓库不上传原始实验数据、论文、正式图/PPT、历史任务台账、冻结评审或软件环境。工作时保留源文件、科学合同、稳定ID与人工冲突；新输出另存，未知结果不自动重放。

本仓库尚未指定开源许可证；第三方依赖遵循各自许可。详见[版权与第三方说明](文档/版权与第三方说明.md)。
