# Learnings

## 2026-10-07: 批量准备按主线交付，环境小问题留证后继续

本轮实现一次清单／固定任务／断点接续，真实三开发素材已完成离线准备；不把原排名报告或微修当新分析结果。夹具须读取实际CLI导出与schema2完整字段，await放列表构建避免异步生成器传tuple；错误已直接更正。Windows state原子替换偶发拒绝属于TD012复现，保留失败与必要窄复查，不加入无证据生产重试、不重跑无变化全套；首次DB前续跑缺口记TD013后继续跨素材检索。用户“按计划大方向、小bug延期”的持久规则已再次核对所有Agent适配及共享记忆。

## 2026-10-06: 主线交付优先，停止在局部bug上反复消耗

用户明确纠正：按总方案与设计路径开发大方向，小bug先记录，能快速修就修，修不了以后修。此前连续检索别称、诊断和局部核对占用了过多时间／tokens，不能继续把微修当主线。每轮以计划里程碑的主要交付为目标，非阻断问题需要重复调查时归档tech-debt并继续；重复完整测试和报告数量不等于项目进展。已提升AGENTS／CODEX／CLAUDE／Grok和agent-workflow，适用于所有项目Agent及会话／工具切换；保留原详细通俗汇报偏好。

## 2026-10-06: 前后文回看不能扩写候选证据或选片边界

Atom11.5–12.5秒近处绿色物体遮着蓝发人物，模型称绿色角色有主体误认风险；相邻注册帧11与11.5／12.5与13秒有场景／镜头变化。周边帧能帮助核对，但未被原候选引用，不能补作模型动作依据或自动声称完整起落。临时前后各1秒回看只改变播放器起止，原行对象／证据／片段篮／导出保持。真实播放与程序夹具分开验证，Agent观察不代替独立人评；已合法多帧且不同hash仍可能主体错误。

## 2026-10-06: 窗口多图不等于候选动作有多帧依据

真实只读审计确认Atom PV旧版移动前十与漫画旧版战斗前十，每条只引用一张登记画面，尽管模型窗口本身曾发送多张图。核对候选自己的注册引用、时刻和内容hash，不能用整个窗口帧数、eventId数量或不同图片证明动作进程。Atom38–39秒多帧实际跨室内外；Agent查看不是独立人评。diagnostics v2仅展示登记数量／跨度／重复或音频状态，动作判断始终null，保留原事实和排名。精确patch上下文必须来自当前实际读取，本轮再次因“候选／诊断”猜词造成整批失败；改用已读文本或整文受控替换，不追加猜测hunk。

## 2026-10-06: 命中字词不等于动作，先读完整原文

扩大已有素材审计时，漫画jump五条命中实际来自JUMP游戏标题和版权文字，非动作标签；root最初仅看计数而误报，核对完整事实后立即向用户纠正。不能因此把English jump补进中文跳跃／英文jumping，有限查询扩展只复用已有中文动作别称。真实实机“起跳”漏掉已有“跳跃”才是可修的词法缺口。解释命中原因前读取原文、标签、源时间和证据，不依计数猜语义。查文档先rg --files定位，PowerShell的文件glob传给rg时使用目录加-g过滤，避免猜路径／字面通配符错误。

## 2026-10-06: 真实素材与检索缺口先从数据库核对

直接核对asset／prompt后确认f601fb9b…33事件为Atom v6，96b5f015…40事件为同一Atom v4；不能因历史任务名称猜为漫画或两个独立v6视频。48词法+10混合只读审计证明英文jumping／move漏掉已有中文文字，是有限检索修复的依据；射击没有文字支持、Boss多个属性没有文字支持，不能据搜索数量宣称源视频没有对应动作或整句成立。源事实／视频真实性、词法支持和独立人评分开取证；新的对照不能提升F006 passes。

## 2026-10-06: 所有 Agent 的持久汇报偏好

用户明确要求每次关键改动后给出不那么技术味的详细汇报，并说明接下来要做什么。适用本项目所有 Agent、子任务、工具切换与会话恢复。先解释使用效果和用户收益，再说明验证证据、剩余问题和下一项具体行动；技术名词和测试数量不能代替说明。规则已提升到 AGENTS.md、各工具入口和 docs/references/agent-workflow.md；持续遵守，不需重复询问。

## 2026-10-06: 近镜头持有物不能被认成人物

用户人工核对接受 detail-query-validation 第一组35–36秒的三个主体描述；指出第二组28–29秒 s1/a2 错误：角色突然拿出物品，物品正抵镜头、遮挡人物并占据大部分画面。这是物品，不是新人物。多帧输入仍可能逐帧误认或把遮挡误作切镜；须核对实际上下文、物品与持有人关系及镜头连续性，不得把输入帧数当作理解正确的证据。反馈只覆盖用户明确核对的条目，不推断其他条目已通过；旧模型结果保持冻结。

## 2026-10-04: Gameplay retrieval must identify temporal actions

User acceptance rejected Boss/jump/shoot search: multi-image inputs produced image inventories instead of action episodes. Existing v2 already sends five frames together, but permits single-frame micro-events. Multiple images, valid JSON, index hits and a usable UI do not prove gameplay understanding. Require source-ordered change evidence and action-level descriptions, distinguish weapon/enemy/pose presence from shooting/Boss fights/jumping, and test static/reversed/cut/unknown controls. Preserve F006 failure and validate new footage results before claiming a fix.

## 2026-10-04: 工作台必须验证完整交互路径

用户反馈：上轮功能测试通过，但时间轴在预览和片段篮下方，选片需反复滚页面，篮子保留点击顺序导致乱序。仅验证按钮/播放/导出不足以证明工作台可用；桌面验收应同时检查三者在常见视口内可见、面板独立滚动和选择后的滚动保持，篮子及导出应明确排序合同。F006检索质量与UI可用性分别记录，不能相互替代。相关文件：ui/static、scripts/validate-inspection-ui.py、sprint-workspace-usability.md。

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20261004-001] best_practice

**Logged**: 2026-10-04T05:30:00+08:00
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Do not merge native stderr when calling `scripts/verify.ps1` from Windows PowerShell 5.1.

### Details
`uv.exe` writes progress such as `Resolved 38 packages` to stderr. The script sets `$ErrorActionPreference = 'Stop'`. Redirecting the script with `*>` turns that stderr line into a `NativeCommandError` and stops the script before Ruff. Run the script directly, or record it with `Start-Transcript`. The receipt check and pytest are unrelated to that failure.

### Suggested Action
Call `./scripts/verify.ps1` without `*>` or `2>&1` when the caller needs the real exit code.

### Metadata
- Source: error
- Related Files: scripts/verify.ps1
- Tags: powershell, verify
- See Also: ERR-20261004-003

---

## 2026-10-04: Switch forwarding and durable inference identity

PowerShell script switches must be forwarded as named typed values (for example -Offline:$Offline), not strings in an argument array. The latter lost offline mode and attempted a package-index request; corrected setup-demo passed entirely offline in project-local directories.

Known model revision and pricing pins belong in the presend fixture metadata. Strict finish_invocation correctly rejected fixtures that changed them after sending. For -I Windows child tests, use explicit -X utf8 rather than assuming PYTHONUTF8 is honored; never hide a decode error with ignore. Keep normal finally-close and intentional os._exit crash behavior distinct.

Parallel follow-up workers must remain in separate worktrees. Preserve newly integrated root edits by giving workers the current checkpoint and copying only owned file diffs back; do not solve ownership conflicts by moving active writers into root.
# [LRN-20261005-001] correction: detailed actor observations and alias leakage

- User accepted better action descriptions but rejected missing appearance/equipment/background/skill detail and visible f0/f1 protocol aliases.
- V4 prompt prioritized actions, input width512 hid small objects, and free-form facts had no alias projection; 16/40 existing Atom events leaked aliases. Do not treat more frames or valid JSON as complete visual understanding.
- Bind visible attributes to their actor and action, preserve uncertainty, validate higher-resolution evidence with versioned profiles, and keep descriptions compact for512-token embeddings. Window-local aliases cannot be mapped from an event's cited subset. Preserve frozen source facts; version any presentation/index projection.
- Shared specification and current work: docs/exec-plans/sprint-visual-details.md. Not a new gameplay quality pass.

