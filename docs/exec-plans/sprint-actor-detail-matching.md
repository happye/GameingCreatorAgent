# F010/TD009：候选主体结构与AND匹配

2026-10-05；owner：detail_retrieval_audit；branch `codex/actor-detail-spec`；worktree `.worktrees/actor-detail-spec`；base `c400188`。
本任务独占新 `actor-detail-matching-spec.md` 与本 sprint；不是唯一开发者，不回写root或覆盖其他Agent变更。
状态：规格b1d91bc→a7789b4已集成，typed合同与纯matcher2e95485→bb05b66已集成；独立合同测试root正在合并/全检。精分析ports/Provider/sidecar/UI与两候选新实验待实现。合同见 [工程规格](../design-docs/actor-detail-matching-spec.md)。

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

用户额度9%提示后进入交接。下一Agent按任务2只先交Application request/result/Provider/Store ports和canonical requestHash，重验当前Completed run的raw candidate/事件fingerprint/注册证据/hash/源时钟；接口冻结后才能并行Provider预算与sidecar。继承旧原始数据，缺结构必须unverified。两候选精分析前处理网络/未知预算：追加第二PV两provider.network造成¥4.065536未确认预留，总本轮承诺¥4.29637520，不能换目录或重试清账；详见HANDOFF。没有新的human labels，F006/F009/F010仍false。

root最终完整verify967passed/1 Windows权限skip（71.87s）、Ruff90/mypy51/CLI/两离线wheel通过，SHA79504099f604bc33810b4bc880ec2f05bf9096fd0b70347019163b02cf80e57d。任务1和独立tests技术合同已整合，任务2开始前以HANDOFF检查当前分支和预算；F006/F009/F010仍false。
