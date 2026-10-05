# Actor detail independent contract tests

2026-10-05；owner `detail_retrieval_audit`；worktree `.worktrees/actor-detail-tests`；branch `codex/actor-detail-tests`；base `47f7de0`。
独占新增 `tests/test_actor_details.py` 与本记录；不是唯一开发者，不修改source、matcher tests、root或冻结的spec worktree。
实现owner为 `detail_v6_completion`，source位于 `.worktrees/actor-detail-contract/src`；最终规格已整合 `a7789b4`。

## 范围与状态

独立工程fixtures覆盖实际lexical `search_timeline`生成的CandidateClip身份、冻结tuple/type/集合上限、SourceRange半开边界与Int64末端、证据/shot/actor关联、静态与动作证据、显式词表/未知类别、版本与canonical query hash、输出报告支持约束。
这些合成fixtures不证明视觉质量，也不提供human labels；没有API、安装或全局配置操作。
两种早期no_match错误已反馈owner，由其matcher tests覆盖；本文件不重复实现这些matcher回归。
此前发现candidate ID缺既有event前缀、蓝色形状词条与报告支持约束问题；owner已修，最新snapshot候选/聚合纯内存复测通过。

## 验证与恢复

root `./scripts/init.ps1`及`-CheckOnly`通过，11项features及本地固定工具链可用。使用root隔离env和Python `-B`，sys.path显式插入owner src，pytest基临时父目录先在root `.cache`建立。
首次pytest 70passed/4failed：owner同时将ConstraintSupport证据字段改为必需，旧构造fixture触发TypeError；已改为显式缺字段负例。关闭cacheprovider产生cache_dir配置警告，后续改用root cache路径。
独立domain tests共73项；canonical JSON与固定SHA golden为`1342b945da41cb36d95f3d6d825d99aba126caf753db55347210ebf8cf736ad8`。
独立短审发现跨run/media及半开边界负例仍留旧nested引用，可能因无关校验假通过；已重建合法nested证据并限定目标错误消息，删去不能独立证明shot上限的重复shot负例，9shot最大合法正例保留。
最终钉owner干净源码commit `2e954850ce088b09835faed67949f150dc42202f`：73domain + 18matcher + 3architecture = **94 passed / 0 skipped，0.32s**。
真实日志：root `.cache/actor-detail-contract-tests/final-2e95485-reviewed.log`；pytest basetemp=`final-2e95485-reviewed`、cache=`pytest-cache`均在该root cache父目录。
Ruff check与format --check通过。测试worktree缺新module时默认分类误认third-party；最终从owner worktree执行并显式使用其未改的pyproject.toml，按默认配置验证合并后的imports分类；没有修改项目配置。
已完成冻结交付，仅提交本记录与`tests/test_actor_details.py`；root集成后运行完整verify。
不改feature_list或F006/F009/F010验收结果；未完成Provider/sidecar/UI/真实精分析与独立人评仍待后续分工。
