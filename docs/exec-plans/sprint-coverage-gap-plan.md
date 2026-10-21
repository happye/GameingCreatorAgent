# Sprint：三组分析覆盖缺口的独立处理方案（规划）

**状态（2026-10-21）：规划完成；用户已选 C；定向补窗离线合同见 sprint-coverage-gap-directed-contract.md；提案草稿模板见 sprint-coverage-gap-proposal-draft.md；只读写出见 sprint-coverage-gap-draft-writer.md；诊断证据链接见 sprint-coverage-gap-diagnosis-link.md。** 选项 C 实现见 sprint-coverage-gap-offline-c.md。本规划 sprint 仍 0 付费、不重跑 launcher、F006/F009/F010 false。B 为未来付费补窗路径。

## Assignment

- Tool/session owner：root／GamingCreatorAgent（单 Agent；规划与公共记录不需专责 Generator／guard，除非后续选定付费补窗方案再分派）
- Branch and worktree：`codex/visual-details`（普通提交，不动 main／不强推）
- Owned files/modules：本 sprint、HANDOFF／assignments／progress／human-inputs 顶部；可选 `.cache/*-publication.json`
- Shared files requiring integration：只读引用 `artifacts/long-analysis-reliability-20261011/*` 与原 run 覆盖文件；**不改** `feature_list.json`
- Dependencies and integration order：先读本文件与终态证据 → 人工择选项 → 若选离线工程再开实现 sprint；若选定向补窗须新提案＋显式授权

## Proposal

### Goal

- 精确盘点接续后仍保留的 **3 组拒绝覆盖缺口**（旧 vision-000021、新 vision-000248／000253）。
- 说明各自为何被拒、isolate 策略是否已记录、费用影响、为何 `completedEligible=false`／非 Completed。
- 给出 **不自动盲目重发同一窗口** 的独立选项，并推荐可先做的离线步骤。
- 同步交接记录，使其他 Agent 可从文档直接恢复。

### Non-goals

- 不重跑新旧 launcher／execute-continuation／execute-authorized-analysis。
- 不发起任何真实视觉模型请求；不把原总 ¥5 余额或已花金额当作补缺口许可。
- 不把 F006／F009／F010 标为 true；不绑定搜索／benchmark／固定人评。
- 不发明真人标签；不强制推送 main；不把 TD012／TD014 当作本 sprint 范围。
- 不把本规划文件本身当作付费授权或实现完成证明。

### User-visible / developer-visible result

- 一份可交接的缺口方案文档；HANDOFF／assignments／progress／human-inputs 顶部反映「接续已推送 ea8b029、本规划已开、下一步等人择选项」。
- 人工只需在 human-inputs 里对 **一条** 待决事项做选择，即可决定下一工程或是否准备定向补窗提案。

## Exact gap inventory（证据）

来源 run：`5c7894aa10e94b8aa82533bd77f9871e`  
策略：`isolate-schema-v1`（`policyHash` `b56f483ae17aade90a4cd272678a1b2fe5460ab4f8b7882b5e2c6eac273cc5f1`）  
覆盖汇总：269 completed／3 rejected／0 unexecuted；`completedEligible=false`  
主证据：

| 证据 | 路径 |
| --- | --- |
| 接续终态 | `artifacts/long-analysis-reliability-20261011/execution-outcome-v1.json` |
| 唯一 guard 实际边界 PASS | `artifacts/long-analysis-reliability-20261011/evaluation-execution-v1.json` |
| 覆盖清单（272 窗） | `artifacts/independent-footage-20261011/runs/5c7894aa10e94b8aa82533bd77f9871e/analysis_coverage.json` |
| P1／接续合同 | `docs/exec-plans/sprint-long-analysis-reliability.md` |
| 接手清单 | `docs/exec-plans/resume-long-zhongkui-20261011.md` |

| stageId | 来源 | 源区间（us） | schema／stop | invocationId | 已知费用（¥） | isolate 记录 |
| --- | --- | --- | --- | --- | --- | --- |
| vision-000021 | 原 run 第 22 窗（接续前已拒，接续 **未重发**） | 73533500–77533501 | `event_frame_boundaries`（事件 2：startUs=77533500／endUs=77533501，实质同帧）；checkpoint `provider.schema` | `b777748f7cea4d2f96b8ddae812bd2ed` | 0.00612692 | 是：拒绝检查点＋费用保留；v2 明确不重发 |
| vision-000248 | 接续新窗（isolate 后 **继续到尾**） | 869067812–873067813 | `event_frame_boundaries`（outcome 中 schemaDetail=null）；`provider.schema` | `cdce533178ee47a594aef0f5ecc69aab` | 0.00618292 | 是：FAILED 检查点保存后继续后窗（P1 实证） |
| vision-000253 | 接续新窗（isolate 后 **继续到尾**） | 886567812–890567813 | 同上 | `43f9e5b8dbef4337b427124c15fa2c4f` | 0.00625892 | 同上 |

**费用影响（累计，非再授权）**：三窗已知拒绝费用合计约 ¥0.01856876，已计入 run 估算总 ¥1.49022124（新接续估算 ¥1.38173400；0 unknown／0 reserved；原总上限 ¥5 未提高）。补缺口若重发，必须另计新请求／新费用上限，**不得**从余额直接扣许可。

**为何 Completed 仍为 false**：合同约定有缺口则终态 `failed/analysis.coverage_gap`（CLI exit 4），写出覆盖清单且 `completedEligible=false`；禁止伪 Completed 导出与正式搜索／benchmark 绑定。P1 已证明「走到尾 ≠ 完整资格」；这是资格保护，不是半途中断。

## Options analysis（独立处理，禁止盲目同窗重发）

| 选项 | 做法 | 影响 | 费用 | 适用 |
| --- | --- | --- | --- | --- |
| **A. 保留缺口** | 接受 269／3；本片不追求 Completed；另用已 Completed 的其他录像做正式 F006（若有）或继续准备其他 pending 片 | 本片不可绑定／人评；理解质量仍未验收 | 0 新调用 | 默认安全；主线可转向其他素材 |
| **B. 定向补窗提案** | 仅对失败 3 窗（或经离线诊断收窄后的子集）写新冻结提案：新 SHA、新费用上限、显式授权、禁止重发 269 成功窗；成功后仍须独立核对覆盖与资格 | 有机会消除缺口→再谈 Completed／绑定；仍可能再次 `event_frame_boundaries` | 须新授权；粗估至少 3 次视觉请求＋帧次，**不得**用旧 v2／余额冒充 | 仅在人工明确要「尽量完整同一钟馗」时 |
| **C. 先离线改进合同／提示／诊断** | 不发送。梳理同帧边界拒因、安全投影字段、是否可改进提示或解析诊断（仍保持多帧合同）；补测试与文档；**之后**若仍要补窗再开 B | 降低盲目重发浪费；不直接消除现有缺口 | 0 付费 | 推荐在选 B 之前或与 A 并行的工程准备 |
| **D. 暂不选择** | 文档停在本 sprint；不实现、不提案 | 无进展风险最低；正式质量路径继续阻塞于本片 | 0 | 额度／注意力不足时 |

**明确禁止**：自动把同一失败窗口再塞进 launcher；用「还剩预算」当重跑许可；猜未保存原始响应里「其他事件有效」；放松多帧／不同源时刻合同来换 Completed。

## Recommended offline next engineering（若选 C 或为 B 做准备；0 付费）

1. **只读诊断包**：从 outcome／coverage／stderr 抽取三窗的白名单投影、帧 alias、事件索引；确认 000248／000253 的 schemaDetail 为何为空、与 000021 同帧模式是否同类（不重放请求）。
2. **合同澄清备忘（已落地）**：见 sprint-coverage-gap-directed-contract.md 与 `directed_gap_fill_inventory`／`validate_directed_gap_fill_targets`；补窗身份 `directed-gap-fill-v1` ≠ isolate 续跑；目标仅 rejected，禁止 269 成功重发。
3. **离线测试夹具／提案草稿（已落地模板）**：见 sprint-coverage-gap-proposal-draft.md 与 `build_directed_gap_fill_proposal_draft`；仍 0 付费，草稿≠选 B。
4. **不改 feature_list**：F006/F009/F010 保持 false，直至另有 Completed 证据与人评路径。

本规划 sprint **不要求**立刻改产品源码；上述为人工选定 C／B 后的建议顺序。

## Acceptance checks（本规划 sprint，非 F006）

- [x] 三缺口 stageId／拒因／费用／isolate 状态／证据路径写入本文件。
- [x] HANDOFF.md、assignments.md、progress.md 顶部反映：推送 ea8b029、本 sprint 已开、下一动作。
- [x] human-inputs.md 顶部仅一条清晰待决（选项 A–D＋影响）。
- [x] `feature_list.json` 未改动（F006/F009/F010 仍 false）。
- [x] 普通本地提交＋（若网络可用）向 `codex/visual-details` 普通推送；可选 `.cache` 发布回执。
- [x] 0 新付费请求；无 launcher 启动。

## Stop conditions and fee gate

- 任一真实模型发送或补窗执行前：**必须**有独立冻结提案＋用户对「该提案费用／图片发送」的明确新答复；旧 v2／「刚才断了，继续工作」／余额均不覆盖。
- 发现需要改产品行为时：停本规划验收，开新实现 sprint；不在本文件静默扩 scope。
- 禁止 force-push、改 main、重抽帧、改原标注、重跑已结束 PID／句柄。

## Review before implementation

- 是否对准当前阶段：是——接续后资格缺口的独立路径，而非再修 P1 中断。
- 失败与成本：盲目重发可能再花约三窗量级费用且仍拒；离线优先。
- Decision：**proceed as planning-only**；实现／付费待人工选项。

## Report to the user after each key change

- 现在能做：查看 269 成功窗的分析产物与覆盖清单；**不能**把本片当正式 Completed 检索验收。
- 限制：3 拒绝缺口挡住完整资格；理解质量／F006 未过。
- 下一步：在 human-inputs 选定 A／B／C／D；选 C 可先离线诊断，选 B 再要具体费用提案。

## Transfer to another tool

- Last commit：本轮提交后以 git 读取。
- Completed：缺口盘点与选项文档、交接同步。
- Remaining：人工择项；可选离线诊断或定向提案。
- Exact next action：读本文件顶部 + human-inputs 待决；**禁止**启动 launcher。
- Owner transfer：root／GamingCreatorAgent；2026-10-21。
