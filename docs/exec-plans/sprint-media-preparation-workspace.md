# Phase 0 多素材准备工作台

2026-10-07，root / Codex，codex/visual-details，接eb73a9f。上一goal turn为progress：联合搜索页面、真实三源／最终2180通过和现用服务已交付；push连接失败不阻断本地主线，goal active。旧worker与worktree冻结，无并行写入者。

本轮主交付F002／F004／现有本地工作台：一行一个本地录像路径，明确目标项目／准备方案／每任务以后分析的上限，提交1–100段离线准备；后台顺序执行不占住页面，逐项进度、显式停止、已保存批次与同ID续跑、打开素材任务。浏览器关闭不自动取消；服务关闭尽力取消并保留既有批次，恢复后显式续跑，不从持久状态冒称任务仍活着。CLI已有媒体准备／冻结／锁／配置／来源与费用边界复用，不增加模型／账本／上传／自动分析。

root独占ui/media_preparation.py新后台任务／安全准备项目与已保存批次读取，server.py新同源有界接口、static/app.js/index.html/style.css、cli/main.py可选原检查点回调，新任务／HTTP／浏览器测试与ignored真实三片证据、指南及公共记忆。只允许仓库artifacts内目标，不服务任意客户端文件路径；源路径是用户明确提交的本地输入，抽取内容留在项目。单服务只一个活跃准备工作，有界注册表、真实线程／协程状态、取消与旧外部项目写锁保持。

验收：新项目／坏项继续／停止与恢复固定任务／浏览器关闭恢复连接／服务无live job时持久历史明确提示、重开不自动执行、错误与同源／路径／配置／预算输入拒绝、原工作台回归；1366／390真实准备及进度／打开素材，无横溢／主要按钮可见。0付费／新预留／人评，旧unknown¥4.065536／新待授权proposal／F006/F009/F010false保持。TD004/005/010/011/012/013按用户主线优先继续延期；不为历史小bug循环微修。

已向用户汇报一次多段提交、每项进度／接续、全本地无模型。下一步复用原CLI检查点并接后台状态／取消，完成页面，再真实素材与完整检查。持续通俗报告使用效果、证据／限制及下一项。

后台主能力已落盘：原execute_prepare_media_batch增加可选已保存检查点回调，未传时原CLI stderr保持；新ui MediaPreparationJobs提供单活跃本地线程／async任务、真实live、显式取消、有界历史、仓库artifacts目标／固定准备方案／输入校验、原批次只读目录及续跑。服务关闭请求取消，不以持久running当活任务；新同源POST提交／取消、GET任务／批次目录均复用原64KiB边界。

20新增后台／HTTP行为在首批全部通过，旧23批次测试中4项遇已记录的state保存／恢复问题（.cache/media-preparation-jobs-first.xml），不更改旧save／加盲重试；后续仅必要一次窄复核，并保留原失败。3源码类型通过，fixture导入／同名参数lint已直接更正。页面、真实素材和最终完整验证尚未完成；现用服务未更新，不能称本轮已可使用。下一步完成新准备窗口与逐项状态／保存批次接续。

## 额度14%可接续检查点：未验收

页面现已实现：路径清单／目标／方案／未来限额、后台逐项进度、关闭窗口或刷新后再连接实际工作、显式停止、持久历史只读与显式原批次恢复、结果下载和打开素材任务。停止／续跑保留原runId及原限额，即使表单输入新限额也不改冻结配置；坏文件不阻断其他材料，关闭或重新读取历史不自动执行。模拟素材全部模型／预留为零，任务仍Pending等待另行分析。

当前服务源码读取静态文件，生产进程尚未载入新路由，因此新增入口初始hidden并只在health明确声明media-preparation-v1后展示。测试覆盖旧后台健康响应没有capabilities时入口仍隐藏、原项目控件可见且不做准备。实际8765只读health仍38216／45800且无capability，没有重启或新增生产任务。本轮不把静态代码已落盘称作部署完成。

验证证据：

- .cache/media-preparation-jobs-first.xml：43项14.266s，20新增全部通过；原23批次4失败，保留。
- .cache/media-preparation-browser-first.xml：4项13.874s／3失败，asyncio.run在Playwright自带事件循环中使用；移到浏览器环境退出后核验，未改产品逻辑凑过。
- .cache/media-preparation-browser-final.xml：4passed13.930s，1366／390布局、三项准备／原限额／零调用、刷新／停止／固定ID接续、坏项继续与历史不自动执行。
- 加新旧服务入口兼容检查时健康请求少/api，首轮出现失败后中止，未生成完整JUnit、未称通过；地址已直接改为/api/health。
- .cache/media-preparation-browser-checkpoint.xml：最终5浏览器＋1原health合同检查共6passed；最终源码对应本回执，具体耗时见XML。
- .cache/media-preparation-old-failure-recheck.xml：四个旧失败仅一次复查4passed1.854s，不称原因修复，TD012保留。
- 项目隔离env下Ruff格式／lint通过，mypy media_preparation.py／server.py／cli/main.py三源码通过，git diff --check通过。仅此变更相关检查，尚无本轮完整verify或wheel。

**未完成且下一会话直接接续：**

1. 使用已有真实三片在独立ignored项目、临时新版服务验证页面准备、逐项信息／下载、坏文件继续与明确接续；复核原素材SHA、原开发项目／查询／费用保持，确保0模型／预留，不操作待授权精分析。
2. 对最终源码运行一次scripts/verify.ps1，检查整套、两个离线wheel及包内文件；有旧偶发失败按TD012仅必要窄复核，不循环微修或重跑无变化全套。
3. 补本地使用指南与真实证据汇报，确认当前原工作台回归。fresh核对8765健康及父子进程、启动记录后更新服务，再检查新按钮／真实准备和原联合搜索。不得按此处旧PID直接结束进程。
4. 再据证据登记交付；feature_list旧passes保持，当前增量验收passed=false，F006/F009/F010false。当前检查点允许提交但不能称功能正式可用。

已向用户按通俗协议汇报：联合搜索真实三片已交付约5.5秒；准备新流程已写完并通过模拟行为检查，真实素材／整套／部署未做；旧bug只复查一次，零费用边界保持。完整阶段汇报report-2026-10-07-quota-checkpoint.md；本地保存／发布事实以Git和.cache/media-preparation-workspace-checkpoint.json为准，上次确认远端5d2a48e，本轮不联网重试。goal active，此次额度汇报不代表暂停／完成整体目标，旧worker冻结。
