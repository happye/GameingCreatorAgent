# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-06，已恢复开发）

goal active：用户已恢复额度并要求持续开发，撤销暂停。当前root在codex/paused-j1-dynamic-preview-20261105，已merge main收尾文档，尚未合main。先读STATUS和docs/exec-plans/sprint-j1-feedback-iteration.md。

恢复检查点：root分支已集成动态策划12浏览器回归、采用期间项目/编辑generation保护（独立4回归闭环）、dissolve及非法布局门禁（独立1回归闭环）。原组合40通过，受影响1174通过/2跳过。新组合初次54通过/3失败已定位：新editor-ready前点击、FFT平滑滞后、安全端口；修后最终58通过，.cache/resume-combined-final.xml。格式/lint/mypy201源通过。下一步完整verify日志.cache/resume-full-verify.log，启动后需核live进程/exec handle，不能重复启动。没有真实付费调用。下文11月5日暂停快照为历史，新的dissolve现已实现，旧“未实现”以本段为准；详细证据见迭代合同11月6日节。

## main：已交付工程检查点

R3界面74a9a72已推送。默认免费本地规则，可显式切AI，准备展示可信已保存EDL文字/报价，逐次确认才发送；提案先预览再后端核父身份应用，用户保存。模式/项目/版本/dirty/text变化作废旧UI，已发送请求可恢复结果，不重新调用。核心a604d09保单次发送、OS锁、不可覆盖attempt、未知费用占用和v4兼容。

完整verify 4813 passed/7 skipped，1237.56秒，格式/lint/mypy198源文件与CLI通过；.cache/reasoning-ui-verify.log。7浏览器+8HTTP+22service+3shell定向40项过。全为fake transport，没有真实AI质量验收或付费调用；J1第四次人评仍not_usable，不能上调passes/交付质量。

第一轮素材/取景/保存/下载/免费声音修复在main，详见迭代合同；原true.txt根因未复现。

## 后续工作完整保存，尚未合并

远端分支codex/paused-j1-dynamic-preview-20261105，8650a23（WIP），含20个源码/测试文件；main已切回稳定版本。恢复可在该分支继续，合并前先同步本轮收尾文档，不能直接当已验收成果合main。

1. 双槽cuts预加载来自.worktrees/j1-preview-corrections：真实206视频0.5/1/2速正确交接、结束；目标seekable等待+实际时间验证+8秒可取消超时。先前跨源从0播失败已修。Sol/high闭环旧slot暂停恢复永久缓冲、seek旧帧覆盖和resultVideo重复增益；13播放通过、helper修正后9确定性过、独立3回归过。证据子树.cache/preview-slot-regressions.xml、preview-slot-deterministic.xml。即时dissolve/双路三角混音未实现；转场禁即时播放但保真实总时长，TD025仍partial。API给run/media派生sourceClock，不改冻结身份。
2. 动态策划来自.worktrees/creation-reasoning-core：PlanSnapshot绑定完整原始brief+候选/来源/范围，1–3案或澄清，后端编译合法区间及准确帧差。独立prompt/schema，复用原有prepare/execute/锁/账本，prepare_plan(jobId)从已完成普通plan读取原始request，adopt_plan(preparedHash)幂等生成普通plan job；采用不再发模型。公开result.planPreview无路径，正式plans receipt留实际provider/prompt provenance。77后端+82旧流程通过，最后13规划再过；核心重复源区间P2已修/独立2回归过，阶段二独立静态审查无可复现新增风险。
3. Studio策划界面及采用竞态现已验证，最新结果见顶段；完整verify仍待完成，不借用旧4813通过冒充新批次结果。

## 运行与保护

8767当前main R3后端，http://127.0.0.1:8767/studio，PID10892（用前核健康/身份）。8766旧后端，8765更旧；此前自动审批拒绝停8765，未绕过。不重试用其他方式杀旧进程。

用户4个未跟踪设计文档未动未暂存。三个旧worktree均保留，.venv/.tools为junction，不盲删。共享venv的editable指主树，树内测试须env后显式设PYTHONPATH=本树src；test-affected会重设，按同一清单直接pytest并记录差异。

Codex只用task_*/harness_*，不复制Claude角色；重复gc-*证据来自客户端external_agent_config_imports，不能推断谁触发。证据/账本/原视频不改不删、不重付重标，不重跑钟馗。

语音免费本机；文本AI仍须每次单独确认，旧¥50分析许可不覆盖。无真实云调用、无Release。推送127.0.0.1:7890代理，不force。指标由python -B scripts/status.py计算，主指标未变化。
