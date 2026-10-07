# Phase 0 多录像搜索工作台

2026-10-07，root / Codex，codex/visual-details，接5d2a48e。上一goal turn为progress：联合排名、CLI与真实三来源验证已交付并推送；继续F005已授权本地检查工作台，goal active。旧worker与worktree冻结。

主交付：明确选择1–100个已完成且不同源的任务，一次联合查询；候选保留全局排名、来源、原时间／事实／不确定性。点击候选先读取原任务再播放其原录像与证据，不另做单任务搜索。旧单任务搜索、按运行独立篮子与源时间导出保持；联合排名提供独立结果下载，不能冒充旧诊断或人工验收。

root独占ui/service.py、server.py、static/app.js/index.html/style.css，新HTTP／浏览器测试、ignored真实页面证据和公共交接。新增有界同源POST复用execute_project_search；目录清单提供来源SHA帮助明确选择版本，同源版本不可同时选。取消／项目切换／参数变化不接受迟到结果。实际验证1366／390尺寸、三开发片、至少两来源播放／证据与篮子／下载归属。

0付费Provider／新预留／人评；旧unknown¥4.065536和新待授权proposal保持，F006/F009/F010false。TD004/005/010/011/012/013延期。关键改动通俗说明使用效果、实测限制与下一项；不重复无变化完整检查。

已汇报本轮选多段录像、一次需求搜索、按原来源回看。下一步完成页面与API，再实际三片验证播放、证据与下载。

实现已落盘：POST /api/search-project有界同源JSON并复用原CLI联合来源核验／独立记录；runs补mediaId／sourceSha。页面显式来源选择、SHA／media互斥、联合结果来源标签、先空查询inspect原run再播／选片、按run独立篮／下载、单录像返回和迟到结果保护。原单诊断在联合范围隐藏，不把候选或片段篮当人工分数。

初步来源接口／双尺寸源切换／音频fallback／独立篮与下载通过；测试夹具的媒体path字段、目录发现层级和手动目录折叠、异步验证字符串受CSP限制均已直接更正，无生产算法微修。最后定向中只迟到测试wait_for_function需用函数而非eval字符串，已改；下一完整检查会覆盖。ruff／84类型通过，真实三源与完整套件仍待执行；现用8765服务尚未更新。已向用户汇报页面流程和接下来真实素材验证。

真实第一轮双尺寸各一次词法查询：674ms／790ms内核、页面点击到结果852ms／866ms，十位含三原来源；六实际原片分别21–22.500001秒／29–30秒／7–8秒，末尾暂停与对应注册图、每源一项篮／下载身份保持。846原项目文件保持、新增2联合查询4文件、原单run搜索214保持，原三个源SHA／proposal不变，0付费／预留／人评。ignored artifacts/project-workspace-validation/report.json。

首批截图拍在最后来源恢复尚未完成的加载状态，追加等待并复用已保存排名校验，0新查询／850文件保持、六播放再次通过。稳定桌面截图发现候选区仅6px，阻碍实际浏览，不能称使用完成。一次完整2179passed／1旧detail-query点击被新布局遮挡失败／1权限skip435.40s；失败与布局一致，非旧环境偶发。新增22行为全部通过，但首次完整并非全绿。直接紧凑搜索布局并新增候选区>=90px断言，下一步定向复核、真实保存排名截图；源码变化后需最终完整检查，新回执与旧首次失败都保留。不重复分析或用视觉漂亮宣称F006通过。

最终紧凑桌面候选区98px、窄屏124px，实际保存排名双尺寸回放六原片、原篮恢复／850文件及214搜索保持，0新联合查询。窄屏选择框受全局input width影响，截图发现后直接固定16px控件并增无横溢／控件宽断言；真实双尺寸选择窗口清晰，source-dialog-report.json记录0查询／0付费。45定向41.185s（含旧失败）和最终3页面复查通过，9前后文回归通过；未靠缩范围或强制click绕过遮挡。

当前源冻结6实现／测试文件SHA在.cache/project-workspace-source-freeze.json；最终完整verify运行中，.cache/project-workspace-final-verify.log／final.xml。此前首次失败保留，不与最终回执混淆。以后只文档／ignored证据／验证／现用服务更新，不在完整检查中改实现。已汇报功能、真实0.85秒／0.87秒、布局修正、原费用保持和下一步更新现用工作台；下一交付建议把多素材离线准备接入现有素材任务清单，不隐式模型分析或越过F006阶段。

## 最终检查与现用服务

最终完整2180passed／1 Windows symlink权限skip320.976s，JUnit2181／0fail／0error；162格式／lint／84类型、CLI及两次离线wheel全部通过，SHA6c6e34bb719b1d01c93596bf1fd17d65af9a239a3aef797fecce3c2d1e2e8fec，83包文件逐字节同源码且无媒体／缓存／DB。源冻结6文件始终相同，最终回执.cache/project-workspace-final.xml／final-verify.log／package.json，首次失败回执保留。源码变化是实际布局阻断，因此最终完整复查有明确理由；完成后不重复无变化整套。

8765服务先fresh health／启动state／父子PID、pinned exe、完整命令行／创建时间验证，再替换40592／11788为38216／45800；三个静态资源字节与最终源码一致，.cache/project-workspace-deployment.json／live-assets.json。现用默认hybrid三来源一次查询、三原片实际末尾暂停／注册图／篮与下载和恢复通过，ignored live-report.json，850旧文件保持只增2记录文件、旧检索214保持。实际本轮共3新项目查询／6文件（2词法＋1默认hybrid），复用保存排名与选择窗口检查0新查询，0付费／新预留／人评。

只读旧漫画任务确认knownUnknownReservationCny=unknownReservationCny=committedCny=4.065536、两unknown attempts／两旧remote requests、billingConfirmedfalse；未知费用与不自动重试保持。新待授权proposal原SHA保持，F006/F009/F010false。桌面／窄屏最终截图由root核对，稳定恢复状态并有源视频／证据／候选可浏览，选择窗口16px勾选、无横向溢出。

现用默认hybrid页面5477ms／检索5074ms，原scope与此前CLI hybrid查询b1d5e5c243d4407a8a57e619eba1f335一致，十候选完整dict（rank／ID／来源／原facts／uncertainty／evidence／interval／scores）逐项相等，prior-cli-ranking.json。本地CPU／硬件成本未测。当前阶段已完整交付，下一root先登记批量离线准备接入现有素材任务流程；不标整体goal完成，原小问题延期与费用未答授权保持。
