# Nested Data Rules v1

animal → section → field → cell；independent culture → well → field → cell，均须保存父子 ID。接受 treatment 的独立层决定推断单位，软件不能从计数猜测。

主图优先一个独立单位一个 approved summary point。先在 analysis 层按批准规则形成 animal/culture/scaffold summary，再跨独立单位形成批准 summary/error。renderer 不聚合 technical replicates。

cell/field 原始数据可以作 faint subsample points、secondary distribution 或 inset，但必须标注 within-unit observations，并保留层级。把 cell count 简写为 biological n 被拒绝。

若主图显示 cell-level observations，必须明确 hierarchy 与 approved hierarchical/mixed-effects model；模型的有效推断信息不能用 cell 数代替。缺少批准模型时，当前门禁阻止 subsample-primary quantitative production。

当前 native nested fixture：3 animals/group × 50 cells/animal，主图仅 3 animal mean points/group；跨 animal 使用批准 sample SD。原始 450 cell rows 完整保存在 OPJU 原始层级工作表。

Image + quant 是 image_plate + quantitative panel 的合同：原图保留 raster identity、scale bar、channel identity、crop provenance、processing provenance。quant 用 Origin native plot。不会矢量化 microscopy 数据，也不新建 assembly engine。


每个需要在主图增加 subsamples 的请求，必须另行规定视觉层级和文字说明；本轮实际通过的 nested fixture 仅画 unit summary，secondary cell overlay 尚未 production-validated。批准 hierarchical/mixed-effects 分析不等于自动获得该 renderer 变体的验证。
