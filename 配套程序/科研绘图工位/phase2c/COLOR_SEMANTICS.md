# Color Semantics v1

categorical group identity 来自已选 B FigureState：Control=#4D4D4D/circle，Material=#0072B2/square，Treatment=#D55E00/triangle。子集不重排组色；跨图型继承身份。

sequential 用于有序单向 magnitude。当前 native heatmap 使用 Origin 自带 Viridis.PAL。

diverging 必须给出有科学意义的 center（例如 signed effect 的 0），并保存范围和 palette。cyclic 仅在角度/相位等确实循环时批准。

连续 heatmap magnitude 不是 categorical group colors。不得把灰/蓝/橙身份色当作 continuous scale。当前 diverging/cyclic native B adapter 未验证；registry 不将它们标 production validated。

字体、字号层级、左/下轴、tick、legend 和 annotation grammar 保持 STYLE_V0_1_SELECTED。heatmap 可为 matrix 标签与色标扩展物理宽度；这一几何 override 不改变 B 的视觉身份。

