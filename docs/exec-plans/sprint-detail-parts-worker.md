# 独立 v3 部件合同离线切片

2026-10-06，owner `detail_parts_v3`；worktree `.worktrees/detail-parts-v3` / branch `codex/detail-parts-v3`。
本切片仅拥有 `deepseek_detail_parts.py`、`test_detail_parts.py` 与本文。root 负责旧 Provider 的三个复用 hook、CLI/API profile、共享文档与集成验证；不回写其他 worktree。

冻结真实 v2 输出把同衣物形状和颜色分成不同 partId，严格匹配器安全但漏掉同衣物复合条件。新增独立 `actor-detail-refinement-v3` 提示词，hash `ce2edb889a4a9f5029c2591e06c210df030fc479d31efff20a4532b2e05f078a`，不猜测合并或改写已经保存的 v2 结果。

公开接口位于 [新 Provider](../../src/gamingcreator/infrastructure/deepseek_detail_parts.py)：`provider_parts_identity()`、`parse_parts_detail(content, request)`、`DeepSeekDetailPartsProvider`。请求版本仍使用已冻结 refinement schema，输出展开为既有 `CandidateDetail`，domain/matcher 不改。

模型 actor 使用 `parts`，每个 part 只有 `partId/partGroup/attributes`；嵌套 attribute 只有 `kind/value/status/evidenceIds`，不再单独生成 partId。`hair/clothing/held_item/action/effect` 各自只能包含对应 kind，partId 在一个 actor 内唯一。每个部件至少一个属性，每 actor 总计最多 16 属性，parts 最多 16；原 9 帧/9 shots/8 actors/16 environment/16 notes 上限继续生效。输入 JSON 字节限制为 1 MiB，重复 keys、非有限值、任意额外字段和未知类别拒绝。

形状、颜色与用途通过嵌套归属于一个明确部件，但共同部件不补充缺失证据。所有范围和 image refs 继续由 v2 parser/domain 从注册源帧生成并校验；跨 actor/shot 不合并，不支持的类型不能借 partGroup，动作仍需两张不同实际图像。相同颜色的两件衣物保留不同编号。模型是否真的正确划分可见物体，仍须真实输出和独立人工核对。

Provider 继承 root 的 `_prompt/_identity/_parse` hooks，仅覆盖独立身份和 parser，复用原单次发送、图字节/hash校验、取消/超时、价格/usage、metadata和未知费用行为，没有复制发送逻辑。root 的 v2 模块在本 worktree 临时复制用于验证，提交前恢复，不属于本 commit。

验证使用 root 项目本地 Python `-B`，dot-source root `scripts/env.ps1`，`PYTHONPATH` 指向 own src，独立 `.cache/pytest-detail-parts` 和 mypy cache：

- 新测试 53 项覆盖同衣物 full、跨部件/同色衣物/actor/shot partial、凸包相交但无共同支持帧、未知与 uncertain、严格嵌套限制、动作及旧 v2 hash不变。
- 新测试加旧 Provider、恢复、共享预算、动作资格与 matcher：**145 passed / 4.24s**。
- Ruff check/format 与新模块 strict mypy：通过。
- v3 成功结果直接复用，attempt metadata 完整；publish 中断恢复零新发送、不重复结算；失败 unknown 保留预留，换 budget 目录不能绕过。
- 全部为本地 fixtures，**零真实 HTTP、零新增费用或依赖**。F006/F009/F010 与人工 quality gate 不更改。

首轮验证 49 passed/1 failed 是测试误写 `ProviderUsage.cache_read_input_tokens`；核对既有合同后改成 `cached_input_tokens`，后续定向全部通过。共享 learnings 的维护权属于 root，已向 root 提交此事实；并非外部调用故障。
