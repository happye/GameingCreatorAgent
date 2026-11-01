# Sprint：覆盖缺口选项 C 离线改进（schemaDetail 并存）

**状态（2026-10-21）：已选 C／已推送 a226bca。** 用户明确选 C：先离线改进，不发 DeepSeek、不重跑 launcher、不标 F006/F009/F010 true。选项 B（定向补窗新授权）保留为以后路径，本 sprint 不执行。

## Assignment

- Owner：root／GamingCreatorAgent（单 Agent）
- Branch：`codex/visual-details`
- Owned：`deepseek_vision.py` 拒因落盘、相关 pytest、本 sprint、HANDOFF／assignments／progress／human-inputs 顶部、诊断报告根因补强
- 不做：付费调用、改 feature_list、放松多帧动作合同、自动重发 3 缺口窗

## 根因（白话）

动作事件要用「开始帧 → 结束帧」圈出一段可剪的片。若开始和结束是**同一张注册帧**，程序会把区间算成 `[T, T+1)`，长度只有 1 微秒，**没有可播内容**，等于空片段。合同要求起止源时刻严格递增；同帧必然 `event_frame_boundaries` 拒绝整窗。三缺口（000021／000248／000253）都是这个模式。

另外：提交 `1e3f420` 在隔离拒绝窗时，把原来的 `schemaDetail` **换成了** `schemaProjection`，导致 248／253 的 outcome 里 detail 为空，诊断变瞎；021 因发生在该提交前仍保留 detail。拒因同类，只是落盘字段回归。

## 本轮已做／要做

1. **恢复并存写入**：`schemaError` 时同时写 `schemaDetail`（有 detail 时）与 `schemaProjection`；多帧同帧拒绝不变。
2. **测试**：隔离续跑测试断言两字段齐全；单帧边界测试断言 projection 与 detail 一致；`schema_detail` 助手要求有 projection。
3. **提示词**：V6 已写明 `startFrameId=endFrameId` 非法；**不改**冻结 hash `a60d114d…`，避免动现有 run 的提示指纹。以后若选 B 要再加强措辞，应另开新提示版本进新提案，而不是原地改 V6。
4. **文档**：诊断包补「根因」；human-inputs 记 C 已决、B 为未来付费路径。

## 仍消不掉的（须以后 B）

- 现有 3 个 FAILED 检查点不会因离线改代码 magically 变成功。
- 模型仍可能再吐同帧；提示已禁止也不能保证。
- 清缺口必须新冻结提案 + 新费用上限 + 你明确批准；禁止重发 269 成功窗；旧 v2／余额无效。

## Acceptance

- [x] 同帧拒绝同时落盘 schemaDetail + schemaProjection；相关 pytest 绿
- [x] 未调用 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] human-inputs 记 C 已决；B 保留说明
- [ ] 普通提交并推送 `origin/codex/visual-details`

## Stop

- 禁止付费；禁止放松同帧拒绝；禁止标 Completed／改 feature_list。
