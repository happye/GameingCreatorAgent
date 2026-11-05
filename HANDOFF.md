# HANDOFF（覆盖快照）

## 当前目标（2026-11-05，Codex）

goal active：按计划持续开发；语音暂用免费本机。不要因一次里程碑结束而标整个goal完成。先读STATUS，再读docs/exec-plans/sprint-j1-feedback-iteration.md。J1第四次人评仍not_usable，没有新真实AI/付费调用。

## 已集成

第一轮J1：原文件SHA归组/分析版本、当前录像默认搜索、独立clipRanges取景与原观察证据分离、3秒建议上下文、片段终点暂停/重播、缓冲时暂停音轨、保存禁用原因、明确下载文件名、本机免费声音默认。原true.txt故障未复现，不能冒称已确证根因。

R3核心a604d09：可信EDL快照、文本提案/澄清、应用前父身份核对、v4链兼容、准备报价/单次明确确认、OS锁和不可覆盖attempt；失败/未知/中断不重发，未知费用保留占用。真实load_chain在async中使用to_thread。

本轮R3界面：server/HTTP端点、Studio默认local可切AI，准备展示实际文字与费用上限；确认后才发送，预览再后端校验应用，用户保存。请求身份随项目/父版本/dirty/行/text变更作废，防ABA。localStorage存最小恢复身份，切模式/刷新可读结果，不再调用；恢复另一条失败时清旧预览。刷新记住具体planId。

全量verify成功：4813 passed、7 skipped，1237.56秒，格式/lint/mypy198源文件、CLI通过；.cache/reasoning-ui-verify.log。7浏览器+8HTTP+22service+3shell定向40项也过。全部fake transport；截图.cache/scratch/reasoning-ui-quote.png、reasoning-ui-proposal.png。未跑Release，不把测试当真人质量验收。

## 正在独立树继续

1. .worktrees/j1-preview-corrections，task_developer preview_dual_player已停止，未集成。修改preview/audio/edit.js、ui/service.py与播放/inspection测试。预加载cuts的fake4项过，真实生成媒体跨源槽位重用后currentTime=2写入却从0播放/output卡2s；复现-k real -q -x -s。preview_parity_design（Astra/low）正在一次升级只读定位。转场仍未实现，树内页面明确需导出观看，TD025未完成。此树含主树R3未提交基线，集成时只取预览增量，不回退R3。
2. .worktrees/creation-reasoning-core，dynamic_plan_core（Sol/medium）已完成新application/plan_proposals.py、tests/test_plan_proposals.py，creative_planner仅提取共用资格函数。快照绑定brief/源/候选/范围，封闭1–3案+澄清，编译真实渲染兼容方案与准确帧差。94相关项、14核心项通过（fake模型）。dynamic_plan_guard（Sol/high）正只读审查身份/重复源段风险，尚未集成，未接provider/service/UI。下一步复用既有单次确认服务，不能复制费用账本或用edit快照冒充新策划。

共享.venv指向主树editable：每次env后显式设PYTHONPATH=本树src；test-affected也会重设，所以按相同清单直接pytest并说明。两树.venv/.tools junction已恢复，.cache独立。第三j1-selected-ranges保留，最多三树；退休先核对成果和junction。

## 保护与运行

用户4个未跟踪设计文档不改不暂存。Codex只用task_*/harness_*，不转换Claude角色；重复gc-*证据为客户端external_agent_config_imports，不能断言谁触发。旧稿/账本/证据不删、不重付重标，不重跑钟馗。

8766是旧后端（R3路由未加载），8765更旧。此前自动审批拒绝停止8765（blocked by policy），没绕过；需要新版服务用安全空闲新端口，不借其他方式重试终止。

所有真实文本AI仍需独立确认，旧¥50分析授权不覆盖。主指标只由python -B scripts/status.py计算。推送用127.0.0.1:7890代理，不force；只暂存自有文件。保持goal active继续动态策划与真实预览。
