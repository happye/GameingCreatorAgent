# AI替换既有镜头

范围：显式AI换镜头；只用已保存父版本与原录影候选文字观察。模型选择S/C别名；服务器重建真实源区间并走prepare_revision/v4，不改账本、媒体字节、时钟或旧请求。

验收：真实revision 8dc5e5b587cf4eb2a6b2005a97c8d6e5 chronological第二段替换武道会1V1候选；其他镜头/声音/图层保持；验证后预览、取消不脏、应用一步撤销重做、v3草稿恢复/v4保存。未知别名、空替换、亚帧、后继转场冲突拒绝；无匹配非修改。

证据：真实源离线快照/prepare/request重建与C55(b524…)2–3秒可信projection通过，父targetClipId保留。根.cache/scratch/ai-clip-replacement-20261117/offline-replacement-projection.json。静态Ruff/mypy/JS语法检查；不跑pytest/全量，不发送模型。实际UI、付费效果、导出验收由主控继续。
