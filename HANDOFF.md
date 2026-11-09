# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-09 晚，Claude Code）

Codex已按用户要求暂停（额度不足）；本会话由Claude Code接手为唯一写者。用户Goal：自主继续开发，关键节点同步Dashboard，需额外授权或无法安全解决时汇报。

## 已完成

- cd60e5c 进度看板：docs/progress/index.html + scripts/progress_ui.py + docs/progress/nodes.json；四工具规则已引用docs/references/progress-dashboard.md。完成模块后改一个节点、运行脚本、同提交。
- 9cb1076 修复Studio成片“下载MP4”裸download属性（htm生成download="true"，即J1“true.txt”根因）；加真实下载属性断言和全Studio模板静态守卫；edit+publish浏览器8过。
- 3b28946 main快进至开发分支并推送（含P018版本对比、TD026留痕、连接队列修复）。全量首轮3个音频测试失败已定向修复；第二轮92%停止记录.cache/knowledge-evidence-hook-fixed-full-stopped.json，不算绿，不同批重跑。

## 等用户

1. 11-09授权的单次动态策划已执行并耗用：.cache/scratch/j1-dynamic-plan-evidence-trial/（execute-authorized.py、real-result.json、diagnose.py、offline-replay-preview.json）。失败因模型抄错指纹；1838938修复。不得重发或自动采用该次；新的Studio动态方案需新的单次授权。
2. J1复测（用户方便时）。

## 下一步（无需授权）

J1剩余工程项均依赖模型或人评；可继续的本机项见看板“还缺”。P011代理清理属.cache清理（用户另有安排），跳过。下一实质业务批次结束时统一跑一次verify.ps1。

## 已知

用户同意AGENTS预算调至8192（22cab2a）。verify.ps1新增同批重跑门槛：.cache/verify-last.json非passed时，除非之后有feat:提交或用户明确要求-AllowRerun，否则拒绝全量。当前记录为84c7341 interrupted；之后已有feat 97c6843，下一次全量属于新批次可跑。

## 保护

未跟踪的用户设计稿/审计报告/Grok工单不动；三子树（creation-reasoning-core、j1-preview-corrections、j1-selected-ranges）与stash b55207b不动。原片/标签/账本/证据不改；不真实发布/支付；免费本机声音；避免PR/AE。推送用 git -c http.proxy=http://127.0.0.1:7890 push。
