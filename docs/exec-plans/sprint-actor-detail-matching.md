# F010/TD009：候选主体结构与AND匹配

2026-10-05；owner：detail_retrieval_audit；branch `codex/actor-detail-spec`；worktree `.worktrees/actor-detail-spec`；base `c400188`。
本任务独占新 `actor-detail-matching-spec.md` 与本 sprint；不是唯一开发者，不回写root或覆盖其他Agent变更。
状态：规格/typed合同/纯matcher、request/ports、sidecar/共享预算与只读检查UI已整合。独立Provider HTTP、typed查询匹配及两候选真实精分析/人评未完成；当前接续见sprint-detail-inspection。

## 已确认问题

真实pilot35s三主体facts经现有lexical对“白发 穿红色外套”返回1条候选，属性属于左/中不同人物。
合成矛盾fixture的facts“蓝色武器”加uncertainty“无法确认是否武器”仍正面命中；uncertainty-only“权杖”不命中。
CLI显示/不确定性与benchmark map已由root修正；raw篮子校验、投影文本hash及向量身份未发现新增兼容缺陷。root V6已Completed：f601fb9b3e734d5ea188fc15c790acbb，33事件；35s候选须实查，缺失可明确选旧Completed V4并独立冻结。
以上是开发复现，未提供独立human labels，不改变F006/F009/F010的false或TD009状态。

## 可分配执行任务

各Agent使用独立worktree；公共现有文件由root修改，下面新模块名称为计划归属，须登记后开工。

| 顺序/owner | 独占文件/责任 | 交付与验证 |
| --- | --- | --- |
| 1 contracts/matcher | 新 `domain/actor_details.py`、`application/actor_detail_matching.py`、对应新tests | typed结构/时钟/局部身份/词表与纯函数AND；fixtures1–5，固定schema/matcher版本 |
| 2 provider/budget | 新 `application/detail_refinement.py`、`infrastructure/detail_refinement_provider.py`、对应新tests | 基于1的数据合同先交request/result及Provider/Store ports骨架，再交prompt/hash与编排；替换fixture、费用/unknown/重试/取消 |
| 3 persistence/UI | 新 `infrastructure/detail_refinement_store.py`、对应新tests；UI/service/static由root集成 | sidecar原子性/锁/幂等/完整性/读边界；fixtures6及真实浏览器附加说明/旧篮子导出兼容 |
| root integration | 现有CLI/UI/共有配置和docs/feature_list | 串行集成、对外入口/版本说明、完整verify、两个有界候选实验及独立人评安排 |

先冻结1的类型与canonical key序列化fixture；2再交公共ports骨架，root集成后2/3并行，不各自发明身份格式；接口变化须通知所有owner。
每Agent保存自己的sprint/commit与复测证据；root只合并独占文件，不能仅凭口头结果通过验收。
检索默认离线；精分析先dry冻结后显式付费，首次只两候选/最多2HTTP，预算和unknown约束按工程规格。
完成技术验证后再安排独立细节人评；复合完全/部分命中分开报告，F006固定十槽规则不变。

## 本次验证与恢复

已读HANDOFF、共享workflow、原方案、Phase0、feature_list、TD009与现有Provider/SourceRange合同。
从c400188创建独立worktree；默认Git写锁被sandbox拒绝，授权范围内升级调用创建成功；没有改用户/系统配置。
`./scripts/init.ps1 -CheckOnly`通过，11项feature；本次仅文档，不安装、不调用API、不重复跑代码测试。
只读子Agent复核后补共同支持帧、未知主体、跨key预算锁与ports依赖；两文件139行、相对链接全部有效、`git diff --cached --check`通过，暂存仅两新文件。
接手先核对root全检与已集成任务1，再从任务2的ports骨架/规范hash开始；勿重复合同或创建新的prompt修旧run。V6 Demo和追加漫画网络失败/unknown预算以HANDOFF为准，不续跑旧failed V5或清零未知费用。
所有实现、独立人评与质量验收完成前，禁止将F010或相关待验特性`passes`改为true。

## 合同实施已冻结，下一步交接

root已集成2e95485→bb05b66实现、410bb245→cd1810c独立测试，两个worktree干净并冻结。schema/词表/query schema/query/matcher五版本均为v1；query canonical JSON与固定SHA `1342b945da41cb36d95f3d6d825d99aba126caf753db55347210ebf8cf736ad8`，供ports复用。新的ConstraintSupport、AttributeConflict、ActorMatch和DetailMatch保留满足/缺失/不确定/反证与共享帧/时钟证明，未接自由文本或UI。

审查修复：现有CandidateClip采用run:event:完整event ID生成，不能自造相似公式；黑发只在f0不反证f1白发，蓝围巾不反证未知外套，属性不越支持范围延续。旧facts/配置/检索/篮子没有迁移。最终独立73domain+18matcher+3architecture=94passed/0skip（0.32s），root完整verify收尾以HANDOFF与.cache/detail-actor-final-verify.log为准。

用户额度9%提示后进入交接。任务2的 request/result/ports/requestHash 已由 root 冻结。Provider 预算与 sidecar 已在文末落地。继承旧原始数据，缺结构必须 unverified。两候选精分析前处理网络/未知预算：追加第二PV两 provider.network 造成 ¥4.065536 未确认预留，总本轮承诺 ¥4.29637520，不能换目录或重试清账；详见 HANDOFF。没有新的 human labels，F006/F009/F010 仍 false。

root最终完整verify967passed/1 Windows权限skip（71.87s）、Ruff90/mypy51/CLI/两离线wheel通过，SHA79504099f604bc33810b4bc880ec2f05bf9096fd0b70347019163b02cf80e57d。任务1和独立tests技术合同已整合，任务2开始前以HANDOFF检查当前分支和预算；F006/F009/F010仍false。

## 2026-10-05 任务2接口冻结

root 在 `codex/visual-details` 新增 `application/detail_refinement.py` 与 `tests/test_detail_refinement.py`。内容只包括 request/result、`DetailRefinementProvider`/`DetailRefinementStore` ports、event fingerprint 和 canonical requestHash。没有 HTTP、SQLite 或 sidecar 写入，没有改 vision prompt 或 raw events。`git diff` 不含 `deepseek_vision.py`。

定向 6 passed（0.37s，`-W error`，缓存在 `.cache/pytest-runs`）。相同输入 hash 相同；改区间或证据 hash 后 requestHash 改变。base prompt version/hash 留在请求旁，不进入精分析 prompt hash，且该 hash 不等于 V5/V6。Completed run `f601fb9b3e734d5ea188fc15c790acbb` 的 `0b8be73b204cceb6f0e37c7d` 保持原区间、注册证据 id、图像 hash 和整数源微秒。非视觉候选 status 为 unverified，shots 为空。旧事件仍进入 inspection 对齐。`init -CheckOnly` 通过。完整 verify 973 passed / 1 权限 skip（69.05s），Ruff 92，mypy 52，wheel `bcc19772b5fe2c85a4c228a5690dce51f48d1a96bfcea756e39b06053edb03a8`。F006/F009/F010 仍 false。没有新 API。

本条历史下一步已完成：sidecar只读详情已接检查接口/UI；后续Provider metadata/恢复与typed查询匹配见sprint-detail-inspection。未知预留处理前不发新API，不宣称玩法/复合检索质量通过。

## 2026-10-05 sidecar 与共享预算

root 新增 `application/detail_refinement_budget.py` 与 `infrastructure/detail_refinement_sidecar.py`。侧车目录是 `runs/<runId>/detail-refinements/<requestHash>/`：不可变 `request.json`、追加 `attempts/<n>-planned.json` 与 `<n>-result.json`、原子 `result.json`。缺侧车为 unverified，不发明属性。哈希、指纹、来源不一致、另一 run 的结果、路径或符号链接逃逸都明确失败，不当成 full，也不删账本。预算在 `detail-refinement-budgets/<budgetId>/ledger.jsonl`，锁只包住恢复、上限检查和预留，发送前释放。未知费用写成 null；恢复和另一个 budget 目录仍计入这笔预留。同 key 已发布结果复用时不再调用 provider，也不再记一笔推理费。显式 retry 保留旧 attempt。没有 SQL migration，没有改 vision prompt 或 raw events，没有 API，没有 retry `0ba106578bc7435c8689d12892a35dfb`。

未完成尝试的判断在 `BudgetWriterLock` 内再次执行。重叠的两次 `send_refinement`（retry 为 false）只有先进入 provider 的那一次继续，另一次是 `budget.interrupted`，不会写下第二个 planned attempt。`tests/test_detail_budget_sidecar.py` 两次都是 9 passed（0.34s）。`tests/test_detail_refinement.py` 6 passed（0.32s），含 Completed 事件 `0b8be73b204cceb6f0e37c7d` 的原时钟。新鲜进程两次 `reuse_or_refuse` 都是 unverified、provider 调用 0，hash `6e9ee8f0c25212e7bd7c401a6dcfa972544e4121494100a7083a2270604c480f`。verify 982 passed / 1 权限 skip（68.06s），Ruff 95，mypy 54，wheel `cf3574ff00d50ffc4df52f0652921ee6fa34160e48b0356aba47320a5fe79330`。F006/F009/F010 仍 false。

## 2026-10-05 Codex接续完成只读检查

继承16f727f、实现96f6c82；sidecar按固定settings/schema/hash接/api/inspect和UI证据页，缺失/旧不兼容数据未验证，已保存结构只展示不标full。新增17项及相关定向88 passed/1权限skip；完整verify999 passed/1skip（142.12s），真实V6浏览器/生产读取通过，0新付费API。完整证据和下一步见sprint-detail-inspection，F006/F009/F010仍false。

更正上一历史节点的目标requestHash：实际为 `229a8bcb9bee1f017854108751d89840f458040fd14cdd3490e5c2fd56d00279`；16f727f模块与当前模块计算完全一致，canonical request无字段差异。此前6e9ee8...无法复现，不能当冻结身份使用；源事件/证据/快照未改，比较报告在ignored artifacts/detail-inspection-validation。
