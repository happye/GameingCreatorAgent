# 结构化条件查询接入

2026-10-06，root / Codex，codex/visual-details；接续已验证精分析Provider23d8422。

root独占typed query JSON codec/离线CLI与match侧车、检查profile参数、对应测试和共享交接；其他worktree冻结。遵循actor-detail-matching-spec，先实现明确typed manifest，不猜自由查询约束。

完成条件：CLI显式输入query-v1清单、指定v1或v2 profile及候选事件；Completed/source校验后只读复用对应侧车，输出full/partial/no_match/unverified及同主体/部件/源帧支持。已有detail可保存独立matches/<constraintHash>-<matcherVersion>.json；缺detail不建侧车、不发Provider、不改原事件/检索/篮子/导出。检查API显式profile参数读取同一冻结版本，默认v1兼容。

## 实现与验证节点

新增match-details命令、严格query-v1 JSON codec和独立match报告/保存；保存幂等且不可改写，不写SQLite/原侧车结果。--profile显式选择v1/v2（CLI默认v2）；/api/inspect新增detailProfile参数（默认v1），读取准确版本而非扫描最新mtime。提供detail-query.example.json。

定向**82 passed，13.08s**，包含新query集成、既有CLI/检查API/纯matcher/架构：完整或部分属性支持、uncertain不升级、缺结构不写不发请求、同义词canonical/hash、错误/超限/OR/否定清单拒绝、immutable match、准确v2 profile。Ruff/mypy58 source files通过；完整verify待运行。实施前Provider完整verify1043/1skip是基线，日志.cache/detail-provider-verify.log。

本地检查点23d8422、记录3b09081已保存；推送3b09081失败（GitHub443连接超时），未更新main，远端暂仍8bcf1ae，后续正常push重试。

仍无新付费API，F006/F009/F010=false，fixture full不表示人评通过；页面自由文本仍未解析为typed约束，精分析付费入口未开放。下一步完整verify和真实V6只读CLI验证，保留精分析缺失的unverified。
