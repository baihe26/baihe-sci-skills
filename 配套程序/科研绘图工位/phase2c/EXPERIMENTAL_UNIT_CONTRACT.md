# Experimental Unit Contract v1

experimental_unit 是独立接受处理、随机化或作为推断单位的对象；不是一行，也不是自动等同 biological replicate。

记录 type、id_column、definition，和 biological_replicate_id / technical_replicate_id / subject_id / sample_id / batch_id；需要时记录 section_id / field_id / cell_id。未涉及的字段写 null，不能编造 donor/animal 身份。

同一样本重复读数、同一 animal 的 sections、同一 well 的 fields/cells、同一 scaffold 的 pores 都不能自动增加独立 n。STATISTICAL_N_IS 必须写单位，by_stratum 的计数必须与原始 ID 去重后一致。

嵌套关系必须无环；每个 child ID 只能对应一个 parent，ID 必须全局稳定或先由分析层构成复合 ID。primary points 的身份数量与批准 plot_data 数量一致。

ONE_POINT_IS 与 STATISTICAL_N_IS 必须同时存在。例如：一个点为 animal mean；n 为 animals。mean/median/混合模型估计由分析层批准，不在 renderer 临时决定。

当前 synthetic fixture 的 animal/batch/sample/particle 是明确设定的测试身份，不是用户真实实验的推断。旧 FigA/FigB 的单位保持 independent synthetic unit，不改称真实动物。

