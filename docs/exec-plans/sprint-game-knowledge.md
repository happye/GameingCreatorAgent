# P018：游戏知识层（本机）

2026-11-01，Claude Code单Agent。

## 合同

- application/knowledge.py：条目字段校验与长度/控制字符限制，来源类型official/wiki/user，entryId=内容SHA256，replaces形成版本链；current/history/search/citation纯函数。
- infrastructure/knowledge_store.py：.cache/workspace/knowledge/<entryId>.json独占创建、永不覆盖；替换必须同游戏且原条目存在。
- GET /api/knowledge?game=&q= 与 ?entryId=；POST /api/knowledge 文本或文件（复用活动规则本机读取）。

## 结果

2026-11-01游戏知识层P018已交付（部分）：创作页新增“游戏知识（本机）”，按需求里的游戏名查找/新增条目（标题、内容、来源类型官方说明/Wiki攻略站/用户资料、来源说明），内容可手填或从本地txt/md/html/截图/PDF读取（复用活动规则的本机读取，不联网）；条目以内容SHA256命名、一条一个文件、永不覆盖，修改生成新版本并记录replaces，可查完整历史，查找只显示最新版本；查找按关键词在标题(×3)/正文中的出现次数排序，每条带“（来源：类型·说明，日期）”，可一键“插入到旁白”（截取前120字+出处）。存于.cache/workspace/knowledge。4项测试（校验、版本/历史、跨游戏隔离、HTTP文本/文件新增+查找+历史+错误）及相关回归共68项通过、Ruff/mypy通过；单Agent。仍未做：规划/解说自动引用知识、联网抓取Wiki、补丁版本对比。51项10/37/4≈56%，首产品0/22/0≈50%；人工0/未来9、债务20项11/2/7不变。下一专业时间线导出（P033）。
## 追加（T21）

2026-11-01：本机目录批量导入 txt／md（可选截图／PDF）；CLI import-knowledge、POST /api/knowledge-import、创作页路径输入；来源含「目录导入」；不联网。自动引用与联网抓取仍未做。

## 2026-11-08：知识进入动态策划（实施合同）

Astra/low只读方案：沿用现有知识录入/检索及单次确认服务，交付“已登记知识→动态策划准备→检查实际发送资料→确认后预览/采用/重开可核出处”。不能把手工复制UI冒充Planner自动引用，不建复杂RAG或新费用/状态系统。root当前P020完整门禁不受此独立分支影响，先收口P020再集成本批。新文字调用仍未授权，本批仅fake transport证明技术路径，不能计真实AI或创作质量。

- 选择：从可信普通plan job的Brief取game、必须主题/目标，复用同游戏current/search与标题权重；仅当前版本、实际命中，空查询/零命中为空。至多3条、每条至多400字连续原文，截段围绕命中；同分同时间按entryId稳定排序。冻结完整entryId、title、source.kind/label、createdAt及实际发送片段。无整库发送/网页抓取/新检索依赖；长中文词法召回限制和零命中如实显示。
- 请求身份：有知识才用v2 snapshot/prompt/proposal，无知识严格沿用v1字节、fingerprint/requestHash及旧记录读回。prepare仅查询一次KnowledgeStore，资料进入实际request.user、hash和报价预览；保守全上下文报价算法不变，不伪称资料越少必然降价。执行/采用/恢复从不可覆盖prepared record里的request.user取冻结资料，重建原job/候选/源校验后核完整requestHash，不重新查最新库、不改旧quote或账本、不自动重发。
- 引用：v2每plan增加knowledgeUses数组，允许空；每项entryId来自本次资料，structureQuote为该plan.structure里的非空原文，拒未知ID/重复对/编造原句。编译报告从冻结资料补出处和原文，不能信模型自填来源。预览、采用结果和重开同时显示策划原句/资料原文/出处。此检查只证明引用对应关系，不核资料真实性或语义结论，不削弱候选画面证据规则。
- 归属：Sol/medium唯一写者preview树新分支；application/knowledge.py、plan_proposals.py、plan_reasoning.py，ui/creation_reasoning_service.py、plan_reasoning_jobs.py必要部分，studio/planning.js及edit.js已采用方案引用展示。测试复用test_knowledge.py、test_plan_proposals.py、test_plan_reasoning_jobs.py、test_studio_planning_browser.py的现有fixture；必要新增具名单文件先说明用途。parent持合同/feature/指南/集成，唯一Sol/high核费用/快照/来源边界，不叠普通审查。范围外文件先报告，函数≤80行，旧付费记录和结果继续可读。
- 验收：同游戏新旧版本/他游戏/无关资料混合时，仅当前命中片段进入quote且逐字可回源；零命中与历史v1保持字节身份。quote后替换库条目，fake确认捕获请求与展示请求完全一致，新quote才选新版本；原视频改变仍拒发送。合法/未知ID、编造原句/空引用各经真实服务校验；合法引用采用并重开可回读，重复采用无新增发送，非法结果不采用。真实Studio走准备→确认→预览→采用→重开，沿现有明确fake模型传输和真实job/收据，不伪造云端质量。覆盖同一边界的场景复用，不扩成镜像测试或重跑全量；父集成时执行完整门禁。

本批不重做整库Studio管理页、联网抓取或独立脚本/Hook/CTA生成；这些最终产品目标仍保留。数据保留本机，任何真实发送到执行前再申请具体许可。

## 2026-11-08 自主恢复收口

唯一task_quality_guard（Sol/high）核知识费用/冻结/来源及Studio草稿边界，通过两项真实P2修复的定向复核。4项旁白定向通过20.79秒，原失败隔离与最终细节见`sprint-studio-narration-revision.md`。完整门禁`.cache/studio-resume-final-r2-verify.log`最终5098通过/7跳过，1760.46秒，静态/CLI通过，520源码/测试冻结hash一致；更早中止及4项测试适配失败日志保留，不作绿证据。P018仍partial，真实AI与人评未提升。

旧 v1 磁盘兼容补证：`.cache/scratch/legacy-v1-compat.py` 在独立目录加载 `8ea3293` 的 `creation_reasoning_service.py` 源码（其基础依赖沿用当前环境），生成无知识的真实 v1 prepared record；当前服务回读 record 不变，经明确 fake 传输执行后实际 user 逐字一致、一次发送，采用/重复采用/新 CreationJobs 实例重开均通过，保留 plan-reasoning-prompt-v1。日志 `.cache/studio-resume-legacy-v1-final.log` 退出0；基线源码hash、quote及隔离仓库路径在 `.cache/scratch/legacy-v1-compat/result.json`。这是基线服务生成的兼容夹具，不是读取或重发用户历史付费记录，也不声称对所有历史记录逐一验证。
