# 结构化条件查询接入

2026-10-06，root / Codex，codex/visual-details；接续已验证精分析Provider23d8422。

root独占typed query JSON codec/离线CLI与match侧车、检查profile参数、对应测试和共享交接；其他worktree冻结。遵循actor-detail-matching-spec，先实现明确typed manifest，不猜自由查询约束。

完成条件：CLI显式输入query-v1清单、指定v1或v2 profile及候选事件；Completed/source校验后只读复用对应侧车，输出full/partial/no_match/unverified及同主体/部件/源帧支持。已有detail可保存独立matches/<constraintHash>-<matcherVersion>.json；缺detail不建侧车、不发Provider、不改原事件/检索/篮子/导出。检查API显式profile参数读取同一冻结版本，默认v1兼容。

实施前已保存Provider完整verify1043/1skip、重复离线wheel及日志；本切片尚未验证。仍无新付费API，F006/F009/F010=false，fixture full不表示人评通过。
