# F010：精分析侧车接入检查视图

2026-10-05（Asia/Hong_Kong）；owner：Codex root；branch/workspace：`codex/visual-details` / root。

## 接续与范围

已读共享规则、工具适配器、HANDOFF、assignments、历史与 `.learnings/`、产品方案、Phase 0、主体匹配规格和架构/环境/测试合同。起点 HEAD `8b71c38`；继承 Grok 的三个未提交 application/infrastructure 模块、两个测试及交接文档，不覆盖或重复实现。

本轮独占 `ui/service.py`、`ui/static/{app.js,index.html,style.css}`、精分析读取接口的小幅补充、新检查集成测试及共享记录。其他 worktree 继续冻结；本轮顺序开发，无新依赖、付费调用或 SQL migration。旧漫画未知预留 ¥4.065536 保留，禁止 retry 或换目录清账。

## 实施前评估与验收

下一条任务按交接只读接入 sidecar：检查响应新增版本化 `detailRefinement`，缺记录/无视觉/未完成 run 为 unverified；有记录按冻结 settings/schema/requestHash 校验复用，不以 mtime 挑版本。没有 typed 查询约束时，即使已复用结构也不标 full。

页面选中片段后展示未验证原因或镜头内主体/部件属性、支持源帧与待核对说明。保留原 observableFacts、区间、证据、rank、篮子与 JSON/CSV 合同。

验收覆盖：空查询/刷新/检索不发 provider、不写 sidecar；成功复用与缺失记录；坏 hash/错身份/未知版本/路径逃逸明确失败；Completed 源/证据完整性；未完成与非视觉不借结构；真实浏览器文本安全、选片/导出兼容及已有真实 V6 smoke。F006/F009/F010 继续 false。

## 当前验证节点

- `git status`/branch/log 已核对，继承的未提交代码归属已确认。
- `./scripts/init.ps1 -CheckOnly`：11 features，通过。
- `./scripts/init.ps1`：固定项目工具与媒体环境可用；Python 打印既有 real-location 诊断，后续以完整 verify 为准。
- 继承的 `test_detail_refinement.py` + `test_detail_budget_sidecar.py` 定向复测运行中；完成后补结果。

## 恢复

先核对 Git 与本 sprint；本轮 API/UI 切片完成后补验证和 HANDOFF，保存本地检查点。未知费用与独立人工质量验收仍需后续处理，不发新推理。
