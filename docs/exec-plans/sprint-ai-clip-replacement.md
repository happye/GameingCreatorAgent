# AI替换既有镜头

R3 · P041、P032 · 2026-11-17 · 已完成真实选择、预览、保存、重开、导出及B站包。

范围：显式AI换镜头；只用已保存父版本与原录影候选文字观察。模型选择S/C别名；服务器重建真实源区间并走prepare_revision/v4，不改账本、媒体字节、时钟或旧请求。

验收：真实revision 8dc5e5b587cf4eb2a6b2005a97c8d6e5 chronological第二段替换武道会1V1候选；其他镜头/声音/图层保持；验证后预览、取消不脏、应用一步撤销重做、v3草稿恢复/v4保存。未知别名、空替换、亚帧、后继转场冲突拒绝；无匹配非修改。

工人离线阶段：真实源快照/prepare/request重建与C55(b524…)2–3秒可信projection通过，父targetClipId保留。根.cache/scratch/ai-clip-replacement-20261117/offline-replacement-projection.json。受影响静态Ruff/mypy/JS语法检查通过；该阶段无pytest/全量或模型调用。后续真实UI、预算内调用及导出证据如下。

主树真实UI：新purpose replacement请求ed7159cc9602abddcae3bf0499284d521632387f3bfa6e835d26cc9e0040063c，预算内一次调用成功，估算¥0.010276。模型选择S2/C55，理由对应俯视方形石制场地与白字“武道会(1V1)”。预览后关闭建议，再只读恢复；应用、撤销、重做、保存6f57066755a04d47b05bbd28b1eb2667，刷新重开并导出0f526cb1e69342edba084fb574c2735b。

真实编辑数据对照仅第2段source range由1–2秒变2–3秒；27段数量不变，其他段来源/顺序/速度/转场及narration/audioMix/overlays逐项保持；旁白仍为原Huihui资产74e4…14.56秒。新目标生成派生clipId，保存前采用父ID。实际输出29秒1280×720 H264/AAC；输出1.5秒帧人工查看确见“武道会(1V1)”石制场地，未凭模型文字认定画面。

保存发布8b8e46a8c76e47319a0a9b6cd958df28，B站包fbe3ab9d83d240ac8ae8beadc0a3f695已生成并下载，七文件齐全。产物目录.cache/scratch/ai-clip-replacement-20261117/：ai-replaced-preview.mp4、bilibili-ai-replaced-package.zip、delivery-evidence.json及截图/响应。旧结果和版本保留，未重发任何旧失败，未实际上传平台，人评不变。

唯一task_quality_guard通过；发现旧rangeProvenance残留阻断预览/保存的P2已修：服务投影显式清旧观察边界，编辑应用仅对替换目标移除无效旧字段。不添加pytest、不运行全量；本批依据为真实操作、源数据对照和受影响静态。单次替换一个镜头，多镜头组合与插入留后续，不将本切片宣称完整开放式编导。
