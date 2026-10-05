# 连续实体与持有关系合同

2026-10-06，owner `detail_parts_v3`；独占 worktree `.worktrees/detail-temporal-entities` / branch `codex/detail-temporal-entities`，基线 `60869d5`。旧 parts worktree 保持冻结。

## 使用效果及已汇报结论

现在能够把“角色”与“角色突然拿出、靠近镜头的物品”分别保存，并记录物品由谁持有、人物何时被遮住以及相邻画面是否连续。匹配白发角色和蓝色扁平持有物时，只有同一角色、同一物品与持有关系共同支持的帧才能提供肯定依据。完全遮挡的帧不能补出发色；物体很大也不能自动成为新人物或切镜。

这能避免把用户28–29秒样本中的前景物品直接升级为人物后，再借属性拼成复合命中。未知实体、不确定角色资格与不确定持有关系完整保留，给集成层提供未解决标记，不能仅根据已知人物的相斥属性宣布所有人物均不匹配。

已向负责人按持久汇报协议说明上述使用效果、验证范围、剩余问题和下一步。公共 `HANDOFF.md`、特性证据与验收状态由 root 汇总；本 worker 未回写共享文件。

## 实际实现

只新增七个约定文件：domain `temporal_entities.py`、application `temporal_entity_projection.py` / `temporal_scene_codec.py`，三个对应测试及本文。现有 CandidateDetail、请求身份、Provider、sidecar、UI和费用不改。

- `TemporalScene` 为不可变、严格有界合同。每个相邻帧都必须有 `continuous/cut/unknown` 与对应依据；cut 只接受 `scene_change` 且两侧图片 hash 不同，unknown 不连接身份。每实体观察必须是注册帧的连续子序列，不能跨 cut/unknown 或静默跳帧。
- 分类为 actor/object/unknown，角色资格接受可见角色结构或两张不同图片支持的独立行为，不要求人类外形。未知分类可保留没有肯定依据的遮挡实体，但只能 uncertain/insufficient_evidence，无 typed 部件。
- actor 部件只含头发、衣物、动作和效果；object 部件只含物体形状/类别。部件内同编号、多属性绑定沿用 v3；分类、属性和 owner 引用都需要 visible/partially_occluded 观察。每连续段最多8 actors，scene最多72 entities/72 owners/16 environment/16 notes，每实体9观察/16部件/合计16属性。
- `project_temporal_scene()` 返回 shots/has_unresolved_entities/notes，不构造 CandidateDetail。程序按非 continuous 边界生成 s1…；仅 observed actor 分类成为匹配 actor。物品属性只取属性与 owner 的共同帧，不确定关系或物品分类只能产生 uncertain 持有属性。生成短部件 ID 避免不同实体同名部件冲突；投影超出既有 actor 16 属性时明确拒绝，不截断。
- `scene_from_model()` 不允许模型提供时钟、base身份或任意额外字段。`scene_payload()/scene_from_payload()` 完整保留分类、观察、关系、边界及注册时钟/hash，限制1 MiB并严格检查版本/整数时钟/集合。

接口/枚举与 model JSON 已提前交付 root。root 负责独立 v4身份、Candidate v2、注册 evidence 与当前请求相等、保存 shots/notes 与重新投影一致，以及未解决实体的 no_match 降级；纯 scene decoder 不掌握外部 timeline 真值，不能自己证明收到的 hash 未被替换。

## 验证证据及限制

先读取新 AGENTS/HANDOFF、人评反馈、总方案/Phase 0、actor spec与agent-workflow；`scripts/init.ps1 -CheckOnly` **11特性 scaffold通过**。使用根项目现有 Python/venv、先 dot-source 根 env.ps1、`-B`、own src PYTHONPATH 与 own cache/basetemp，不安装或改系统。

81项新测试 **81 passed / 0.18s**；六文件 Ruff/格式检查及三源文件 strict mypy通过。反例包含缺失/逆序/重复/跨镜头引用、遮挡提供分类和属性、未知及错误类型、物品变actor、不同人的物品、关系/属性凸包相交但无共同帧、uncertain owner、静图假动作/agency、真实cut与unknown边界、超限、完整roundtrip和model禁时钟。单帧角色结构允许，单帧动作仍拒绝。

全为开发 fixtures，零真实 HTTP、零新费用/依赖。程序可以确认结构和引用正确，不能确认模型解释视觉真伪；新增合同没有证明用户标错样本已理解准确。独立模型对照、人评及Phase 0门槛仍未通过；冻结v1/v2/v3与旧未知预留不变。

## 下一步与恢复

root 集成独立v4 Provider与版本化持久读取，然后验证页面可核对角色/物品/遮挡/切镜依据、未知状态及费用兼容。真实实验须新冻结候选/注册输入，明确目的地、预算和请求次数；当前离线切片不使用已经执行完的旧两次授权。worker提交后冻结本 worktree，避免集成期间接口漂移。
