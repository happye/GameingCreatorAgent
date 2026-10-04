# Active assignments

协调规则见 `docs/references/agent-workflow.md`。2026-10-04用户指定Codex接续Grok检查页，当前root负责最终集成和共享记录。所有本轮worker已冻结，禁止从旧scratch覆盖root；当前分支/推送状态见HANDOFF及git。

## 当前交付

当前新增F008：root在codex/workspace-usability拥有app.js、验证脚本和共享记录；workspace_layout在.worktrees/workspace-layout/codex/workspace-layout拥有index.html/style.css及自己的sprint。acceptance_deployment只读核对。其余历史worker仍冻结；F008验收前不标true，见sprint-workspace-usability。

| Feature / owner | Branch/worktree | Owned files | State / evidence |
| --- | --- | --- | --- |
| F007 / Codex root | main，root（origin/codex/inspection-workspace备份） | ui/server.py、service.py、media.py、storage port、HTTP测试、浏览器脚本及共享文档 | accepted / 2bb9848已同步main；sprint-inspection-workspace.md |
| F007 / inspection_frontend | codex/inspection-frontend，.worktrees/inspection-frontend | ui/static/{index.html,app.js,style.css}、sprint-inspection-frontend.md | frozen / integrated：0d9e3c5→9fcbdec，3e5c8e2→614c10d |
| UI / ui_review | 只读root | HTTP/路径/证据I/O/费用复核 | done；3项发现均修复并回归 |
| Docs / docs_audit | 只读root | 根指南/规格/手册/架构一致性审查 | done；过期状态由root修正 |

F000–F005及F007技术合同已验收。F006工具已实现，独立人工quality gate仍false；选片篮不替代humanLabels。

## 已整合历史任务

| Feature | Owner | Historical branch/checkpoint | Evidence |
| --- | --- | --- | --- |
| Demo / F003 / F005 | Codex root | main：19cfe58，origin/codex/phase0-demo备份 | sprint-demo.md |
| Pricing / vision / docs | demo_pricing | worker整合进root | sprint-demo.md |
| Local retrieval | demo_retrieval | codex/demo-retrieval：4b692d8 | sprint-F005-worker.md |
| F006 runner / SQL3 | demo_benchmark | codex/demo-benchmark | sprint-F006-worker.md、sprint-F005-persistence-worker.md |
| Retrieval v3 / initial UI | Grok Build | 未提交修改由root保留在32d5a3b | sprint-inspection-workspace.md |

旧Grok/F003及其他scratch worktrees仅保留历史、已冻结。新并行任务须先登记独占文件并建立独立worktree；公共规格、依赖和交接由root串行整合。接手不得把历史owner当当前占用，先核对git和HANDOFF。
