# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-09，额度恢复后续做）

Goal active。用户明确恢复，要求继续手头任务，余量接近10%时再次停止收尾；之前未及时停成功导致额度耗尽。已找到本地当前CODEX_THREAD_ID的session日志token_count.rate_limits；.cache/scratch/read-codex-quota.py只输出本线程最新primary/secondary余量，取较低值，12%开始收尾、约10%暂停。不可用时不猜百分比。

## 当前版本对比批次

root分支codex/knowledge-version-compare-20261108，已推源码检查点732a6ae；main仍36d8325，上批知识/旁白完整5098过7跳。新P018逐行比较已实现：GET/api/knowledge before/after、同游戏/未知ID校验、不可变两侧出处、Studio显式选择/原文/增删与未变行。唯一Sol/high通过，受影响29过1跳（symlink unavailable），最后布局/两ID与时间定向1过4.16s、Ruff/mypy209过；见sprint-knowledge-version-compare.md。

旧门禁session84919已不存在、OS无pytest；.cache/knowledge-compare-full-verify.log停91%，52%一个F，无summary/nodeid。现场b45b447ffd2841428cf755fb3febc2f2缓存为空，不能定位失败，不作绿，不删除。只读探索已确认这点，不重复猜测。

新完整门禁用独立Hidden pwsh PID42072运行：.cache/knowledge-compare-resume-full.log（-vv -rA逐项）、knowledge-compare-resume-full.xml、knowledge-compare-resume-exit.json终态。PID文件knowledge-compare-resume.pid；先核进程与exit文件，不因工具session失效重启。启动脚本.cache/scratch/resume-knowledge-verify.ps1。verify.ps1新增可选-PreserveRuns，仅跳过旧目录prune/成功目录删除，所有门禁未变，唯一Sol/high静审通过；本次启用以保护旧失败现场。源码/测试仍匹配knowledge-compare-freeze.json，resume-manifest附verify脚本hash。新进程结束后按明确失败nodeid定位，完整绿前不推main。不得因旧日志F推断是业务问题或强行合并。

## 已授权单次真实文字试跑（尚未执行）

用户已明确“允许这1次，上限¥2.02”，后要求暂停，现又明确恢复；无需重复索取同一许可。仅preparedHash 9bcc9d01729bf0e59ff4934fdacaf5f6ed74c12147b1741c95eb0fa83bc0dcea：漫画群星既有完成run f76f5d6495314c04ae04083614d4afd6，新60秒本地job e01c7683a5eb4e5590adff9f129ba620 ready无缺口，74候选文字/时间/身份，不发媒体，知识命中0故v1。DeepSeek Flash最多一次、无自动重试，报价2.016384<=授权2.02。真实发送0，密钥只核bool存在，未输出。

预览/摘要/approval-status在.cache/scratch/j1-dynamic-plan-authorization/；旧10秒预览不用于本授权。恢复发送前核原请求/源hash、最新官方价格及是否已有attempt/result，沿现有硬门禁execute，不能重付。价格已于11-08核同固定快照，费用unknown不写0。human-inputs记录为已授权非新人工待办；预算¥50仅录像分析，不套入文本。

## 保护与后续

未跟踪用户设计稿/审计报告/Grok工单不动，不整目录add。3子树均脏，不reset/复用/删除覆盖；stash b55207b68ce12b3682607687c54dc818d1f6f849不drop/pop。原片/账本/标签/旧证据不改删，不重跑钟馗，不真实发布/支付。旧8765–8769不动、8770已清，不绕过停服拒绝；避免PR/AE，启动桌面程序先说明。并行写者独立树，子树env后显式本树PYTHONPATH，完整验证只root。

先收口版本对比与上述一次已授权试跑，不因人评未完成停止其他已授权开发。P018仍partial，质量/人评/Release未提升；主指标和计数以status.py为准。后续停止前先落盘/推开发检查点与短交接，再update_goal paused，不能把问答工具accepted当授权或把未终结验证当绿。
