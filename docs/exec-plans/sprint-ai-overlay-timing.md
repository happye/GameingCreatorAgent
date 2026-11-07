# AI 编辑独立图层时间（工作树实现中）

2026-11-07，延续 J1 “logo消失太快”的修改需求与 R3 自然语言时间线路线。先给已保存的独立文字/PNG图层提供结束时间及淡出建议，保留已有镜头修改；后续操作仍按完整路线扩展。本批不能定位、拆分或抠除原录像里已烘焙的logo。

## 合同

1. 自由文本沿用现有文字模型准备/逐次确认/执行/结果恢复/验证流程，不新增关键词路由，不发真实调用。图片层身份不证明它是logo，目标不明时澄清；无独立图层的旧请求仍要求视觉身份不明时询问，不能删源镜头冒充去除logo。
2. 仅对有已保存图层的新prepare使用 `creation-reasoning-overlays-prompt-v1` / `creation-reasoning-overlays-v1`。v1 SYSTEM/context逐字节保持；旧prepared即便父含图层，也按存储的版本配对重建旧snapshot与requestHash，拒绝未知配对，恢复不重发。
3. Chain.edl不含图层。新snapshot显式加入 `overlaySnapshotVersion`、完整overlays及按assetId去重排序的底层asset.public()，校验集合/receipt/kind/text/尺寸；所有字段参加fingerprint。模型投影仅给图层id/文字/位置/输出帧/必要尺寸，不给assetId、路径、receipt或imageUrl。
4. 新response精确增加overlayEdit。`overlay_edit_proposal`只有一个已存在overlayId及整数endFrame/fadeOutFrames，clips/questions为空，citations仅该图层ID；其他kind的overlayEdit为null。拒绝多余字段、bool、越界、无改动与资产注入；完整selection由服务端复制可信图层并只改这两字段，复用domain重验。
5. 预览临时图层，不改editing.overlays或dirty；取消/需求/项目/版本变化恢复。明确应用再次核父receipt、purpose、fingerprint，validate返回可信完整selection，客户端原子提交clips+overlays草稿，再由已有保存/重开/导出链落盘。
6. v4仍保留verified candidate manifest及replacements空选择路径，图层提案用原clips；clip-only提案继承原图层，剪短后越界拒绝，不自动截断。音频和其他图层保留，不更改费用闸门或账本。

## 归属与验证

- Astra/low只读架构合同；其最初把图层误归EDL的判断已纠正，以实际Chain独立字段为准。
- backend子Agent连续两次Bad Request，parent接手，唯一实现树 `.worktrees/j1-preview-corrections`；Sol/medium前端在assets树持有三JS/新browser test，parent已复制到preview树联合验证。
- backend旧88项、新14项，以及前端/后端/旧AI UI联合21项通过；新增v4原clips/manifest保留及未知版本拒发通过。fake transport或fake HTTP只证明协议/流程，不证明真实模型理解这些同义表达。
- 真实本地HTTP→fake文本transport→验证/应用→保存/刷新→真实FFmpeg导出1项通过（preview树`.cache/overlay-ai-e2e.xml`）；原1秒结束延长到3秒，输出第60帧绿色PNG像素证明2秒位置仍显示，确认前0调用、确认后仅1次fake请求。不是云端质量验收。
- 唯一Sol/high边界审查通过（源码/XML，未独立跑pytest）；root先完成P028完整门禁再集成本批及最终门禁。未合main，未改passes/人评/交付状态，真实云调用0。
