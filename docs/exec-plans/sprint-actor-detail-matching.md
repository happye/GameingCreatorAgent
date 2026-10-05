# F010/TD009：候选主体结构与AND匹配

2026-10-05；owner：detail_retrieval_audit；branch `codex/actor-detail-spec`；worktree `.worktrees/actor-detail-spec`；base `c400188`。
本任务独占新 `actor-detail-matching-spec.md` 与本 sprint；不是唯一开发者，不回写root或覆盖其他Agent变更。
状态：工程规格待root集成，代码/新实验尚未实现。合同见 [工程规格](../design-docs/actor-detail-matching-spec.md)。

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
接手先读工程规格并分配任务1；已有V6真实试验/demo进度以root HANDOFF为准，不续跑旧failed V5。
所有实现、独立人评与质量验收完成前，禁止将F010或相关待验特性`passes`改为true。
