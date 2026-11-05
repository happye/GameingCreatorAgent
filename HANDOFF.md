# HANDOFF（覆盖快照）

## 暂停状态（2026-11-05，用户要求）

goal paused：用户额度不足5%，要求暂时停止并收尾。不要自行继续开发；用户恢复后从本快照接续。先读STATUS和docs/exec-plans/sprint-j1-feedback-iteration.md。

## main：已交付工程检查点

R3界面74a9a72已推送。默认免费本地规则，可显式切AI，准备展示可信已保存EDL文字/报价，逐次确认才发送；提案先预览再后端核父身份应用，用户保存。模式/项目/版本/dirty/text变化作废旧UI，已发送请求可恢复结果，不重新调用。核心a604d09保单次发送、OS锁、不可覆盖attempt、未知费用占用和v4兼容。

完整verify 4813 passed/7 skipped，1237.56秒，格式/lint/mypy198源文件与CLI通过；.cache/reasoning-ui-verify.log。7浏览器+8HTTP+22service+3shell定向40项过。全为fake transport，没有真实AI质量验收或付费调用；J1第四次人评仍not_usable，不能上调passes/交付质量。

第一轮素材SHA归组/分析版本、当前录像搜索、clipRanges独立取景与原观察保护、短事件建议上下文、片段终点暂停/重播、音轨缓冲、保存原因、下载名及免费本机默认都在main。原true.txt根因未复现，不冒称已确证。

## 后续工作完整保存，尚未合并

远端分支codex/paused-j1-dynamic-preview-20261105，8650a23（WIP），含20个源码/测试文件；main已切回稳定版本。恢复可在该分支继续，合并前先同步本轮收尾文档，不能直接当已验收成果合main。

1. 双槽cuts预加载来自.worktrees/j1-preview-corrections：真实206视频0.5/1/2速正确交接、结束；目标seekable等待+实际时间验证+8秒可取消超时。先前跨源从0播失败已修。Sol/high闭环旧slot暂停恢复永久缓冲、seek旧帧覆盖和resultVideo重复增益；13播放通过、helper修正后9确定性过、独立3回归过。证据子树.cache/preview-slot-regressions.xml、preview-slot-deterministic.xml。即时dissolve/双路三角混音未实现；转场禁即时播放但保真实总时长，TD025仍partial。API给run/media派生sourceClock，不改冻结身份。
2. 动态策划来自.worktrees/creation-reasoning-core：PlanSnapshot绑定完整原始brief+候选/来源/范围，1–3案或澄清，后端编译合法区间及准确帧差。独立prompt/schema，复用原有prepare/execute/锁/账本，prepare_plan(jobId)从已完成普通plan读取原始request，adopt_plan(preparedHash)幂等生成普通plan job；采用不再发模型。公开result.planPreview无路径，正式plans receipt留实际provider/prompt provenance。77后端+82旧流程通过，最后13规划再过；核心重复源区间P2已修/独立2回归过，阶段二独立静态审查无可复现新增风险。
3. 父控新planning.js+edit接入+CSS也在WIP分支：按已保存需求准备/确认/预览/采用，最小恢复身份存localStorage。**尚无动态策划Studio浏览器测试/视觉QA；组合后尚未跑受影响/全量。** 集成中格式/lint/mypy201通过发生在最后UI接入口改动之前，不替代这些待办。下一步先写新UI真实HTTP+fake模型纵切片（确认、恢复、dirty、ABA、采用幂等），再定向/整仓，必要修复再合并。

## 运行与保护

8767当前main R3后端，http://127.0.0.1:8767/studio，PID10892（用前核健康/身份）。8766旧后端，8765更旧；此前自动审批拒绝停8765，未绕过。不重试用其他方式杀旧进程。

用户4个未跟踪设计文档未动未暂存。三个旧worktree均保留，.venv/.tools为junction，不盲删。共享venv的editable指主树，树内测试须env后显式设PYTHONPATH=本树src；test-affected会重设，按同一清单直接pytest并记录差异。

Codex只用task_*/harness_*，不复制Claude角色；重复gc-*证据来自客户端external_agent_config_imports，不能推断谁触发。证据/账本/原视频不改不删、不重付重标，不重跑钟馗。

语音免费本机；文本AI仍须每次单独确认，旧¥50分析许可不覆盖。无真实云调用、无Release。推送127.0.0.1:7890代理，不force。指标由python -B scripts/status.py计算，主指标未变化。
