# 结构化条件查询接入

2026-10-06，root / Codex，codex/visual-details；接续已验证精分析Provider23d8422。

root独占typed query JSON codec/离线CLI与match侧车、检查profile参数、对应测试和共享交接；其他worktree冻结。遵循actor-detail-matching-spec，先实现明确typed manifest，不猜自由查询约束。

完成条件：CLI显式输入query-v1清单、指定v1或v2 profile及候选事件；Completed/source校验后只读复用对应侧车，输出full/partial/no_match/unverified及同主体/部件/源帧支持。已有detail可保存独立matches/<constraintHash>-<matcherVersion>.json；缺detail不建侧车、不发Provider、不改原事件/检索/篮子/导出。检查API显式profile参数读取同一冻结版本，默认v1兼容。

## 实现与验证节点

新增match-details命令、严格query-v1 JSON codec和独立match报告/保存；保存幂等且不可改写，不写SQLite/原侧车结果。--profile显式选择v1/v2（CLI默认v2）；/api/inspect新增detailProfile参数（默认v1），读取准确版本而非扫描最新mtime。提供detail-query.example.json。

定向**82 passed，13.08s**，包含新query集成、既有CLI/检查API/纯matcher/架构：完整或部分属性支持、uncertain不升级、缺结构不写不发请求、同义词canonical/hash、错误/超限/OR/否定清单拒绝、immutable match、准确v2 profile。完整verify **1062 passed/1 Windows文件symlink权限skip，93.59s**，Ruff103/mypy58/CLI/重复离线wheel通过；日志.cache/detail-query-verify.log。此前Provider1043/1skip为基线。

本地检查点23d8422、记录3b09081已保存；推送3b09081失败（GitHub443连接超时），未更新main，远端暂仍8bcf1ae，后续正常push重试。

本节点尚无新API；后续授权实验见下方。F006/F009/F010=false，fixture full不表示人评通过；页面自由文本仍未解析typed约束，付费入口未开放。

2026-10-06节点：wheel SHA `f4282ed7b02c315a3d2cb6c8acd16d8cd4bddd2ada9c655cda9970123a1be799`，最终再次读取两wheel哈希一致；仅README/交接更新，不参与wheel元数据，无源码变化或重复pytest。真实V6只读CLI v1/v2均unverified，33原事件/证据/运行文件无改写；报告artifacts/detail-query-validation/real-read-report.json。

已冻结规格中两个候选，proposal artifacts/detail-query-validation/pilot-proposal.json。用户明确授权追加最高¥4.04，仅这两个候选，每个1次/总2次，不自动retry；旧未知¥4.065536保留。独立v2请求hash分别dc31fcc36cfc4c0f1fc064ec30db399636723552806349e05e38b0add024fd13与2d0b267fac0b8a390486678c57aea98b409b1018f7b8e4a3199fc74d0c48efce；每次保守预留¥2.016384，合¥4.032768。官方中文价目与2026-10-04冻结快照一致；页面直读超时后官方搜索结果复核成功。无凭证GET api.deepseek.com返回401，证明可达；仅报告凭证存在性，不输出凭证。

首次执行被自动审批在CreateProcess前拒绝：预算/候选授权未包含具体素材目的地，0请求；用户随后明确允许6张注册画面、帧ID及提示词/参数传往https://api.deepseek.com/chat/completions后才执行同一命令，无绕过。两次均Completed，无retry：主体区分¥0.008513/5663ms/1249输入+1816输出；持有物¥0.00999312/5632ms/2404输入（256缓存）+1960输出。合计估价¥0.01850612、unknown0，不是账单；base events/evidence/invocations不变。全任务已知¥0.24934532+旧未知预留¥4.065536=承诺¥4.31488132；不清除旧账。估价使用[官方中文价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)的已冻结版本，不是账单。

两个查询均partial；武器类别追加离线查询也是partial，没有新API。主体区分未跨actor合并白发/红衣，但模型每个属性用了不同partId，真实同衣物形状/颜色尚不能严格合并；下一版需改善part合同，不能自行合并已冻结输出。持有物场景记录蓝发与蓝色扁平物、三shot；白发条件未满足，具体观察交给用户判断。humanLabels/qualityGate仍null，F006/F009/F010false。

本地ignored证据：pilot-report.json（完整attempt/typed payload/match）、pilot-proposal.json（冻结请求）、两份query JSON及human-review.html（6帧/模型观察/两项核对题）。HTML内嵌原帧、不请求外部服务；1366与390宽无横溢、0页面错误，human-review-desktop.png已视觉检查。生产服务身份核对后仅重启旧49020/35808；新PID36320/parent24836与状态文件/health一致，v2 API读取33事件，0新API。下次重验PID。

完成后以拒绝Provider fixture再次send这两key，均reused/0新调用，sidecar与ledger哈希完全不变；reuse-report.json保存真实复用证据。每key只有attempt1，没有清除预留或覆盖immutable结果。

两次授权调用次数已用完；无第三次或retry。下一步独立人评、离线新版本part绑定和页面typed入口/成本历史。GitHub两次push超时，a6eb196与前序提交暂只在本地，最终同步状态以后续Git核对为准。
