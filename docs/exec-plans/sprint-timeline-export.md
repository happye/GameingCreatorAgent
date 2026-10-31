# P033：专业时间线导出

2026-11-01，Claude Code单Agent。

## 合同

- application/timeline_export.py：layout按整帧修剪交叉淡化（左N//2、右其余），转场起点=剪切点-左侧帧数，总长=Σ帧-Σ重叠；源起点按自身速度平移。
- to_fcpxml：resources format/asset+media-rep文件URI，spine asset-clip/transition，变速timeMap；to_otio：Timeline/Stack/Track/Clip/Transition/ExternalReference，变速LinearTimeWarp，importVerified=false。
- GET /api/creation/jobs/<id>/timeline?planId=&format=fcpxml|otio 作为附件下载。

## 结果

2026-11-01专业时间线导出P033已交付（部分）：编辑器“导出已保存版本的时间线”提供FCPXML 1.9与OTIO JSON下载（GET /api/creation/jobs/<id>/timeline?planId=&format=fcpxml|otio）。按原片文件URI与源时间写入，时间为输出帧对齐的有理数；变速写timeMap/LinearTimeWarp；我们渲染时交叉淡化是两段重叠N帧，而两种格式要求片段首尾相接、转场居中借用余量，因此在剪切点按整帧修剪（左N//2、右其余），导出总长与真实成片完全一致。真实34镜头版本导出FCPXML 34段、时长299/30秒=成片9.97秒，OTIO 34段。4项测试（整帧布局与总长、FCPXML结构/转场/timeMap/文件URI、OTIO总长与转场、HTTP下载）通过、Ruff/mypy通过；单Agent。仍未做：在Final Cut/DaVinci/Premiere里实测导入（本机无这些软件，故只记部分），Premiere XML（xmeml）、字幕/配乐/旁白轨道导出。51项10/38/3≈57%，首产品0/22/0≈50%；人工0/未来9、债务20项11/2/7不变。

## 追加

2026-11-01 P033推进：时间线导出新增Premiere XML（FCP7 xmeml v4，format=xmeml），与FCPXML/OTIO共用整帧布局：片段起止帧、源入点、文件路径、居中交叉淡化transitionitem；xmeml没有固定倍速属性，变速片段保持准确时间线长度并在名称里注明“导入后请在软件内设置速度”。编辑器导出链接增至FCPXML/OTIO/Premiere XML。5项导出测试通过、Ruff/mypy通过。三种格式仍未在剪辑软件中实测导入。计数不变：51项10/41/0≈60%。
