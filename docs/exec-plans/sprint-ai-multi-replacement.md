# AI 一次多镜头替换（2026-11-17）

## 范围与验收

沿用 purpose=replacement 与现有预览/应用入口。新 prepare 使用 creation-replacement-v2 / creation-replacement-prompt-v2，一次响应 selections 内列出 1 至父镜头数的 S/C 配对；目标不重复，只允许 1x cut 且后继 cut 的目标。clarification/unsupported 必须 selections=[]。拒绝未知别名和额外字段。

v1 snapshot/request/system/body/hash 保持原函数及字段不变；恢复按已存 prompt 版本选快照。插入复用旧 replacement_snapshot/request，不继承 v2。新结果 kind 仍 replacement。

所有 replacements 一次交给现有 manifest + prepare_revision + project_clips。仅更新目标区间；v5 后继明确 insertions=[]；继承旁白、混音及图层。未改变费用、授权、账本及保存流程。

## 已有证据

- 独立树 ai-multi-replacement，根虚拟环境加载 env 后以 PYTHONPATH 指向本树 src，实际 import 路径已核对。
- 真实只读父 24e685643eb449f19af360542c0bd6d6 / chronological：S1→C1、S2→C2 一次投影通过，28 clips、2 replacements、insertions=[]；没有保存或付费调用。
- 与 HEAD 原模块对照：v1 snapshot fingerprint、request 全字段及 insertion snapshot fingerprint 相同。
- 重复 target、未知 target、非修改带 selections 拒绝。
- 首次验证 S1/C7、S2/C8 被既有 Duplicate source interval 保护拒绝；v2 已增加私有候选源区间与最终全片区间预校验，组内重复及撞未修改行均在 validate_proposal 阶段拒绝，不产生 completed。v1 与底层保护不变。真实数据两类冲突均拒绝，候选源身份未进入请求正文。
- 三个改动 Python 文件 Ruff check / format 与 mypy 通过。未运行 pytest、全量、模型、安装、commit/push。

## 集成待办

主控负责 UI 多镜头说明、真实模型与浏览器应用/保存/导出链路，以及关键边界独立审查。当前证据为真实数据本地投影，未宣称人评通过。


## Prompt v3 冲突提示（2026-11-18）

新 prepare 使用 prompt-v3/schema-v2，snapshot 仅新请求加 source-interval-aliases-v1 策略标记。请求候选按目标时长输出 conflictsByDurationUs：只列最终区间已被哪些 S 别名占用，不发送源 SHA 或源时刻。冲突镜头可以同时换离，保留合法交换组合；最终 validator 仍验证全片区间唯一。旧 prompt-v2、v1 与插入快照重建路径保持。

已付请求 b991bc…28ace 的失败原样保留，未重发；只读重建其原 fingerprint/requestHash 通过。该输出 S1/C74 与未改 S19 同为原片50–51秒，实际为候选冲突。新 v3 离线核对 C74.conflictsByDurationUs[1000000] 包含 S19，候选字段无源身份；Ruff/format/mypy 通过。真实新调用及链路由主控另行推进，不回放该失败。
