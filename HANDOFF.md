# HANDOFF（覆盖快照）

## 暂停（2026-11-09，用户明确要求）

用户额度不足7%，要求把重复全量问题同步Harness并收尾。当前开发与验证均暂停，不自行续跑；原Goal已清除，不创建或恢复。恢复先读STATUS/AGENTS Testing与git状态。

## 必须遵守的纠正

根AGENTS.md Testing已强化：默认失败node IDs/真正受影响文件；全量只在实质业务批次收口。全量失败先定向修复，复用其它已通过证据，不因单项修复、提交、文档或“闭环/必须全绿”自动再全量，不把修失败改称新批次。同批第二轮全量须用户明确要求，平时直接推迟到下一实际业务批次，勿制造确认请求。Release分发要求保留。CODEX/CLAUDE/Grok适配器只引用这一共享规则，新对话同样生效。

## 本次两轮全量及有效证据

用户“继续开发，额度46%”后共2次verify。第一次.cache/knowledge-evidence-batch-full：5108过7跳3失败，2229.875秒；CLI未运行。3项均audio_preview_graph_browser：HOOK幅度失败提前退出留下2个audio，后两项清理断言级联。旧日志/目录保留，不作绿。

84c7341仅修测试：HOOK_CAPTURE换AudioWorklet，保持0.4秒及原阈值；加600ms主线程阻塞/渲染帧连续性，fixture finally卸载，业务audio.js未改。旧采样回归0.029572vs0.1稳定失败；整文件10项连续三轮通过（27.951/27.794/28.160秒），独立Sol/medium通过。.cache/hook-clock-original.xml及hook-repeat-1/2/3.xml。已有证据足够覆盖这次局部修复，不要再跑三轮或全量。

第二次.cache/knowledge-evidence-hook-fixed-full在约92%按用户纠正停止，PID40844及其6个子进程已停止，记录*-stopped.json（21:55:50+08）；未形成完整终态/CLI，不算绿，不得重启它来“收口”。536文件freeze、日志都保留；scratch/finalize-knowledge-evidence-records.py只适用全量成功，当前不能运行。中途监控曾漏报第一轮早期失败，不能从尾部PASS推整体绿；最终事实以完整XML或明确停止记录为准。

## 已保存业务能力

分支codex/knowledge-version-compare-20261108；业务/测试检查点84c7341已推，main仍36d8325，未集成/Release。本批P018同游戏逐行版本比较、原文/出处、迟到隔离已实现，唯一边界审查通过，受影响29过1跳；TD026先留parsed output/receipt再验证、受控错误及SHA引用已实现，旧无ref兼容，组合60过、受影响脚本82过、唯一Sol/high通过；真实旧失败记录只读恢复11文件hash不变。队列128解决默认5连接积压，真实模块突发及规则浏览器22过。合同sprint-knowledge-version-compare.md、sprint-paid-output-evidence.md。当前不提升人评/质量/整项交付。

恢复后复用上述完整与定向证据，推进实际开发和交付记录；不得把自定“全量绿前合main”当作自动重跑理由。需额外验证时只选真实影响范围，下一实质批次再统一全量。

## 费用与现场保护

原一次¥2.02许可已耗用：preparedHash 9bcc9d01729bf0e59ff4934fdacaf5f6ed74c12147b1741c95eb0fa83bc0dcea，Provider完成但应用失败，估算¥0.05877非实扣对账；原输出丢失不可恢复，原result/receipt/账本不改。本轮无新增付费调用。

免费准备的新请求7abf86df0b4458a22b7482806e15799b277e89285aa11cbeecb4230da5aabf3a在.cache/scratch/j1-dynamic-plan-evidence-trial/，74候选文字、保守报价2.016384。未申请/收到新许可，发送0次，不执行execute-once.py，也不为其自设全量前置重启测试。新调用仍须新明确许可，旧一次许可不适用。

GitHub直连失败，单次git -c http.proxy=http://127.0.0.1:7890 push可用，未改全局配置及Provider网络。Harness当前有并发新增dashboard/环境说明改动，和未跟踪docs/progress、progress-dashboard.md、scripts/progress_ui.py；保留原样、不替其提交。仅分离暂存本次Testing纠正。其余用户设计稿/审计报告/Grok工单、三脏子树、stash均不动。原片/标签/账本不删改，不重跑钟馗，不停8765–8769，不启动PR/AE，不真实发布/支付。
