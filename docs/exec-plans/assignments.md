# Active assignments

## 2026-10-06 断网接续：离线部件、条件页面与费用历史

| Owner | Branch/worktree | 独占范围 | 当前状态 |
| --- | --- | --- | --- |
| root / Codex | codex/visual-details，root | UI/service/server/static、typed HTTP、页面集成测试、共享文档、最终整合 | 接续998bc2d；页面明确条件匹配及profile选择，零Provider调用 |
| detail_parts_v3 | codex/detail-parts-v3，.worktrees/detail-parts-v3 | 独立v3精分析prompt/parser/provider模块、新v3测试、own sprint | 新嵌套part合同；v2模块/冻结结果不改，不发送HTTP |
| detail_cost_history | codex/detail-cost-history，.worktrees/detail-cost-history | 新只读精分析费用历史模块/测试、own sprint | 恢复planned承诺，未知不清零；不改UI/service或账本，不发送HTTP |

旧worktrees保持冻结，编码worker仅在各自worktree写入。root串行整合profile及API，不降低验收门槛；原两个真实调用次数已用完。当前远端已核对30c44ae，998bc2d为本地状态记录，后续按实际Git同步。

2026-10-06 root / Codex完成Provider/record codec/sidecar恢复23d8422、typed query CLI/match侧车/profile a6eb196；最新完整verify1062/1权限skip，定向167与82通过。两个明确授权真实候选各1次均Completed/partial，合估价¥0.01850612/unknown0；旧预留¥4.065536保留。人工核对入口artifacts/detail-query-validation/human-review.html，见sprint-detail-query。root继续负责离线part合同/页面typed入口与成本历史；历史worktree冻结，禁止额外API或retry，F006/F009/F010false。30c44ae已正常push并独立核对远端SHA，main不改，后续仅状态文档同步。

## 2026-10-05 当前细节优化

当前 root `codex/visual-details`，起点72d692b；以下覆盖旧任务的当前占用。共享证据见 `sprint-visual-details.md` 与 HANDOFF。

2026-10-05 Codex 顺序接续 Grok 未提交的 sidecar/预算实现；新增只读检查视图任务归 root，独占 UI/service/static、读取接口补充、新集成测试及共享记录，见 `sprint-detail-inspection.md`。其他 worktree 保持冻结；无新 API，F006/F009/F010 仍 false。

| Owner | Branch/worktree | 独占范围 | 状态 |
| --- | --- | --- | --- |
| root / Codex顺序接续Grok | codex/visual-details，root | analysis/config/store/CLI/UIprofile、detail sidecar/budget、只读检查UI/测试、共享文档 | 继承16f727f/实现96f6c82；只读详情接入完成，定向88 passed/1权限skip；完整verify999 passed/1skip，真实V6浏览器与生产读取通过。无新API |
| detail_vision | codex/detail-vision，.worktrees/detail-vision | deepseek_vision.py、新 detailed tests、own sprint | 56b02e2→903c9cc 已集成并冻结；root补证据范围保护 |
| detail_presentation | codex/detail-presentation，.worktrees/detail-presentation | observation_text.py、retrieval.py、ui/service.py、app.js、新 presentation tests、own sprint | a160116→86c229c 已集成并冻结 |
| detail_pilot | codex/detail-pilot，.worktrees/detail-pilot | validate-visual-details.py/new tests/own sprint | 944fb42→32fe12c 已集成并冻结，真实V5对照完成 |
| detail_v6_completion：旧任务 | codex/detail-v6，.worktrees/detail-v6 | deepseek_vision.py/new eligibility tests/own sprint | dff948e→02cb7b2已集成冻结，禁止回写root |
| detail_v6_completion：新合同 | codex/actor-detail-contract，.worktrees/actor-detail-contract | 新domain/actor_details.py、application/actor_detail_matching.py、test_actor_detail_matching.py、own sprint | 2e95485→bb05b66已集成冻结，21定向通过；无API/UI接入 |
| detail_retrieval_audit | codex/actor-detail-spec，.worktrees/actor-detail-spec | 新actor-detail-matching-spec.md、sprint-actor-detail-matching.md | b1d91bc→a7789b4已集成冻结；只读复核完成 |
| detail_retrieval_audit：合同反例 | codex/actor-detail-tests，.worktrees/actor-detail-tests | 新test_actor_details.py、own测试sprint | 410bb245已集成冻结；73domain+18matcher+3architecture=94通过/0skip |
| detail_pipeline_audit | 只读 root | 根因/细节/旧数据身份审查 | 已完成，无编辑或 API 请求 |

Atom新V6 f601fb9b3e734d5ea188fc15c790acbb Completed：16窗口/33事件/估价¥0.10270124。查询/浏览器及新版启动器复用已验证，当前PID49020/parent35808仅快照，下次重验health。全任务已知¥0.23083920；漫画run0ba106...两网络失败未知预留¥4.065536，总承诺¥4.29637520，已停API。typed matcher/request/ports、sidecar/共享预算与只读检查视图已实现；Provider HTTP、typed查询匹配与自由查询约束未接。旧rawfacts不改；F006/F009/F010仍false。

下一条工作：离线实现独立精分析Provider及完整attempt metadata/恢复合同；typed查询匹配随后接入。未知预留处理/明确新预算前不得新API，不宣称玩法/复合检索质量已通过。当前记录见sprint-detail-inspection。

协调规则见 `docs/references/agent-workflow.md`。2026-10-04用户否决玩法检索。当前root分支`codex/temporal-gameplay`已保存Grok4c37a63、帧边界42604f9/b2daf1b与启动器0cc2c2f；共享记录以HANDOFF和sprint-temporal-gameplay为准。禁止旧worker覆盖root；推送状态以git核对。

## 当前交付

最新Atom run96b5f01530ce43e2944828fb0520b9b4已Completed，16窗口/40事件；最新verify744 passed/1权限skip，启动器与修正后真实浏览器通过。否定误召回已修，jump hybrid2，仍待人工判断；F006/F009仍false。只读Grok复核与v4合同审查完成，无文件改动。

| 当前 owner | Branch/worktree | 独占范围 | 状态 |
| --- | --- | --- | --- |
| root / F009 | codex/temporal-gameplay，root | 集成、config/store/analysis/pilot、UI/API、共享文档 | 新run/3个有界对照/启动器已验证，质量未通过 |
| temporal_frame_contract | codex/temporal-frame-contract，.worktrees/temporal-frame-contract | deepseek_vision.py、test_temporal_frame_contract、own sprint | d026103→42604f9；冻结 |
| workspace_launcher | codex/workspace-launcher，.worktrees/workspace-launcher | Start-Workspace.cmd、start-workspace.ps1、test_workspace_launcher、own sprint | df475ef→0cc2c2f；冻结 |
| retrieval_negation | codex/retrieval-negation，.worktrees/retrieval-negation | application/retrieval.py、test_retrieval_negation.py、own sprint | b1e33a5→5f15bab；冻结；原事件/embedding/阈值不变 |
| temporal_vision | codex/temporal-vision，.worktrees/temporal-vision | 已交出 deepseek_vision.py、test_temporal_vision.py | 冻结在 bdf3861 加格式化差额；不要回写 root |
| temporal_pilot | codex/temporal-pilot，.worktrees/temporal-pilot | 已交出 validate-temporal-gameplay.py、test_temporal_pilot.py | 冻结在 ca45f1d；不要回写 root |
| temporal_audit / temporal_acceptance | 只读root | 根因、官方模型/价目、验收设计 | done，无文件改动 |

当前config.temporal.example.json的promptHash与v4一致：9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48。旧v3实验/配置hash记录是历史证据，不用于新run。

历史下一句已由上面的精分析端口任务取代。不把有效 JSON、candidate 数量或浏览器检查当玩法通过。

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
