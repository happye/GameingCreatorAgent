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
- 继承的 `test_detail_refinement.py` + `test_detail_budget_sidecar.py` 连同本轮读取补充定向复测：15 passed/0skip（0.75s）。沙箱内首跑卡在 asyncio 本机 socketpair 初始化，faulthandler 已定位；中断两次本工具启动的测试后允许本机回环重跑成功，未改产品事件循环。
- 已保存继承检查点 `16f727f`。检查接口/UI与17项新回归已实现；Ruff与mypy 54源文件通过。首个集成回归发现旧短ID兼容和schema1 fixture丢hash，已修正，保留旧合同。后续新测试15项读取/坏hash/未知版本/设置隔离/源篡改/逃逸已通过；最后两项浏览器fixture原放在发现层级之外，已调整为既有 `artifacts/*/timeline.sqlite3` 深度，待复测。
- 一次复测在sessionfinish碰到Windows pytest cache临时目录rename权限失败，已改为预建本轮独立cache目录，不删除/改权限、不忽略warnings。完整verify前保留此失败证据。
- 修正后集成复测：86 passed/1 Windows文件symlink权限skip/2 failed（18.07s）；最后两个浏览器检查发现JSON导出原有spread会夹带新增detailRefinement，已显式剔除。UI仍从当前视图读取详情，篮子持久化和schema1导出不携带结构，待最终复测。
- 最终相关定向回归 **88 passed/1 Windows文件symlink权限skip（18.18s）**，其中本轮新增17项全部通过，含真实浏览器安全文本、已保存属性/uncertain与支持帧、同run篮子恢复及原事实导出。Ruff格式/检查与mypy54源文件通过。
- `scripts/verify.ps1`补预建本轮cache目录，防止本次实测的pytest cache rename权限故障；只改项目临时目录准备，不降检查或改宿主配置。完整verify与真实V6 smoke即将运行，结果待补。

## 恢复

先核对 Git 与本 sprint；本轮 API/UI 切片完成后补验证和 HANDOFF，保存本地检查点。未知费用与独立人工质量验收仍需后续处理，不发新推理。

## 最终评价与交接

- 实现保存于96f6c82，继承Grok实现保存于16f727f；共享记录另存docs检查点，最新HEAD以git log为准。
- `./scripts/verify.ps1`（本机回环授权，Start-Transcript记录）：**999 passed / 1 Windows文件symlink权限skip，142.12s**；Ruff96文件、mypy54源文件、锁/工具收据、CLI和两次离线wheel通过。wheel SHA `431d9f32f5c774ffecb351d2d55f50a4a7a1fbdd72bc9787cb7c40c4efc05b0e`。日志 `.cache/detail-inspection-verify.log`。uv提示缓存位于源码目录，wheel仅打包src规则与既有隔离合同保留，没有新增依赖。
- `python -B scripts/validate-inspection-ui.py --project artifacts/demo-phase0 --run f601fb9b3e734d5ea188fc15c790acbb --query "黑色高礼帽白色面具角色挥动指挥棒" --output artifacts/detail-inspection-validation/browser`：passed；33事件/3候选，播放结束暂停、源图、筛选、篮子源序/恢复、JSON/CSV、1440×900/1366×768三区同屏及390px无横溢，0JS错误。
- 只在health/保存状态/父PID/项目Python路径与命令一致后停旧服务42408，启动新版49020/parent35808；`.cache/workspace/port-8765.json`一致，`start-workspace.ps1 -NoBrowser`已复用。该PID是快照，下次重验，未开用户浏览器或发推理。
- 生产只读报告 `artifacts/detail-inspection-validation/production-read-report.json`：旧V2/111、V4/40、新V6/33事件均读取新版本详情字段，真实数据尚无精分析结构，全部missing/unverified；默认V6，选片显示未验证提示，0JS错误。三份semantic timeline快照与sidecar文件前后相同，原事件区间/证据保留。截图production-detail-status.png。
- 真实目标事件requestHash与旧交接值不一致，经只读加载16f727f源码与当前源码比较，canonical request逐字段相同，两者均为 `229a8bcb9bee1f017854108751d89840f458040fd14cdd3490e5c2fd56d00279`；旧6e9ee8...无法复现，文档更正，未改变源事件或hash算法。证据request-identity-comparison.json。
- 未验证：真实精分析Provider HTTP、完整每attempt metadata/发布恢复与typed QueryConstraint匹配入口、独立人工细节/玩法质量。reused只由合成侧车验证，不能说真实主体精分析已完成。F006/F009/F010仍false，¥4.065536未知预留和漫画failed run保持原账。
- 下一条具体任务：独立精分析Provider的冻结prompt/parser与完整metadata、取消/中断恢复先做离线fixture；随后typed matcher接入。真实调用先处理未知预留/网络或得到明确新预算，不自动重试或換目录清账。

用户随后明确授权仅推送codex/visual-details到https://github.com/happye/GameingCreatorAgent。普通HTTP/1.1 push已成功，新建远端工作分支并上传00f279654a396f3730ed780b827cf650e3d550d3，未更新main或强推。紧随独立ls-remote因GitHub443连接失败（约21s）未确认；同步记录提交后再次核对，最终分支HEAD见Git。先前自动审批拒绝由用户明确授权解决，未绕过审核或改全局配置。
