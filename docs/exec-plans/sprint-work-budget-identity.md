# 作品身份与创作预算归属

P019 / P021 / P039 / TD029 · 2026-11-13 · active

交付目标：同一作品的需求理解、反复生成根方案、AI策划、修订与导出始终使用同一视频预算；显式新建作品才取得独立身份。月度¥30、同视频跨月¥1不变。

## 已选设计

- 素材项目projectId可包含多条作品。显式“新建作品”以客户端稳定requestId（32位小写hex）作为workId；服务端幂等落盘，刷新/失败重试不得生成新ID。旧草稿继续原预算路径，不自动转换成新作品额度。
- work记录放在既有creations根下works/，不可变，含schemaVersion/workId/projectId/createdAt和整体文档hash。采用既有根路径/链接保护、local_files读取/独占写入及ProjectWriterLock。损坏记录拒绝，不自动替换身份。
- 需求准备纳入projectId/workId；根plan带workId；AI采用/修订/render从可信父链继承，不接受冲突的跨项目/跨作品身份。prepared记录使用新字段时纳入原hash；旧记录哈希与回放路径保留。
- 新works有独立work:预算键。旧brief-unassigned不能猜归属，仍按保守规则；所有确认尝试仍计入原月份总账。新work首次创建后无需承担无法归属的旧brief，但恢复旧根不能借新ID清零。
- 新prepared将已核实的budgetKey冻结进原整体hash；历史消费优先读取该冻结键，不随以后job链的可变状态重新归属。发送时仍复核当前来源链与冻结键一致。旧prepared不增字段、不重写hash，沿旧版本路径读回；损坏或来源身份不明不能靠换jobId自动获得额度。
- 可信legacy根的新prepare同样冻结原根jobId预算键；旧无冻结记录严格解析原根，坏链记为全局未知归属?。不得在解析失败时退回中间jobId重新给额度。
- 根plan只可引用已创建、同project的workId；派生任务从可信父链继承。预算身份解析至少核对本地request整体digest与项目归属，不为此重复读取原录像字节。没有可信来源链时拒绝自动费用路径，既有结果只读恢复不因此触发重付。
- 公共API为POST /api/creation/works exact {projectId,requestId}，GET /api/creation/works?projectId=...及GET /api/creation/works/<workId>?projectId=...；GET /api/creation/work-scope?projectId&jobId核对任务所属作品。只创建身份不调用模型；相同创建请求可幂等重试。POST先验证已发现项目，再落盘。作品查询不冒充job status。
- 工作台需求草稿/最近job/待恢复AI请求按workId隔离；切换/新建作品清理旧异步应用路径。当前作品恢复先读服务端记录，不能只信localStorage。完整多轨工程回放另片实现。

## 所有权与验收

- 第一独立实现仅WorkStore及其单元测试；集成前不算产品交付。
- 总体验收必须包含A作品需求→两次根plan→AI采用→render，刷新/服务重启后续用；临近¥1并发只放行预算容许调用；显式B独立单条/共享月上限；恢复A余额延续；旧根链和孤立brief/未知成本兼容；账本字节不改；损坏/父链冲突不自动付费。
- A跨月仍累计¥1；A/B并发临近共享月¥30时，只放行合计预算允许的发送。已消费prepared的来源链之后变动，历史消费仍归冻结budgetKey；未发送prepared变更来源链时自动与显式execute均拒发，已有result可只读恢复。
- prepared损坏导致冻结预算身份不可读时，未知归属消费保守占用所有视频额度或拒绝自动发送，不能退回新jobId取得独立¥1。
- 主题编排批次完整verify已通过5226/7skip。本片已集成到主树，Ruff/format/mypy通过；最新预算作用域/完整旅程/浏览器组合33过，受影响检查及本片完整门禁待完成。此前导航回归最后一步未展开方案分组的夹具错误已修，未改变业务断言。

## 验证进展

受影响94文件：1078 passed、3 skipped、1 failed（旧测试要求把A项目迟到状态显示在B项目）。保留任务登记/原草稿不变断言，改为验证B不显示A状态；该节点与最终作品浏览器回归合计9过，修复闭合。导航消费只在恢复effect判断，不改变仍挂载编辑器的open依赖，切布局保留dirty修改；关键边界增量静态审查通过。新版完整门禁待运行，尚不提升交付/人评状态。
