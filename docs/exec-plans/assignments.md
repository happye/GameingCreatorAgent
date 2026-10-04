# Active assignments

协调规则见 `docs/references/agent-workflow.md`。2026-10-04用户否决玩法检索。root 已把 vision/pilot 的独占文件集成到 `codex/temporal-gameplay`，共享记录以 HANDOFF 和 sprint-temporal-gameplay 为准。两个 worker worktree 冻结，禁止再把它们覆盖回 root。本轮未提交、未推送。

## 当前交付

| 当前 owner | Branch/worktree | 独占范围 | 状态 |
| --- | --- | --- | --- |
| root / F009 | codex/temporal-gameplay，root | provider、pilot、时序测试、config.temporal.example.json、公共文档 | 已集成并完成一次有界对照；F009 仍 false。verify 618 passed、1 skipped |
| temporal_vision | codex/temporal-vision，.worktrees/temporal-vision | 已交出 deepseek_vision.py、test_temporal_vision.py | 冻结在 bdf3861 加格式化差额；不要回写 root |
| temporal_pilot | codex/temporal-pilot，.worktrees/temporal-pilot | 已交出 validate-temporal-gameplay.py、test_temporal_pilot.py | 冻结在 ca45f1d；不要回写 root |
| temporal_audit / temporal_acceptance | 只读root | 根因、官方模型/价目、验收设计 | done，无文件改动 |

磁盘复核：`config.temporal.example.json` 的 promptHash 等于 `vision_prompt_fingerprint("phase0-vision-v3")`；两次 dry-run 为 `frozen`，execute-1 为 `completed_with_failures`。

下一条工作：查看 `artifacts/temporal-gameplay-execute-1` 里 window-0-B 的 `evidence_outside_range` 拒绝，收紧 v3 提示让被引用帧落在半开区间内，先用离线视觉测试证明，再对同一个四秒窗口重跑一次有界 `--execute`。不要全量重分析 PV，不要把 F006 或 F009 标成通过，不要宣称打Boss、跳跃或射击已经修好。

下面F007/F008为已交付历史，不是本轮占用；恢复见sprint-temporal-gameplay。F006用户定性验收未通过，正式U10未运行；F009false。

F008技术验收已通过：87637af同步origin/main与origin/codex/workspace-usability，317b22d为主线交接；workspace_layout的5a44dfd/7ad1321已集成1bf8881/600276e并冻结。acceptance_deployment/visual_review只读核对已完成。证据sprint-workspace-usability。

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
