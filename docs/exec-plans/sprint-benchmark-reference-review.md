# Phase 0 分析前的原片人工参考标注

2026-10-07 root / Codex，codex/visual-details，接799625c；上一goal turn为progress，批量准备页面已交付并普通推送。当前仍F006前置资料／原片人工参考，旧worker冻结。初查已有冻结／绑定、候选评审和固定原排名计分均已实现；缺口是冻结前参考事件与可用区间只能手写JSON。实际素材目录有7段，不能因文件数／名称猜独立录制组、用户已看结果状态或人工可用事件。

主要交付：独立本机原片标注HTML，在模型分析前按事前查询回看原片、填写真实动作ID／归组／可用区间和理由、保存并继续标注；核对记录与源身份后导出benchmark-plan-v1给既有freeze。原查询／来源／分区／同源和已看结果声明不由标注自动改变；人工确认／填写人／标签版本显式填写，不自动打分或认证独立性。没有人工记录只能空模板，ready不是F006通过。0Provider／预算／搜索／上传，不读模型输出或分析数据库。

root独占新application/benchmark_reference_review.py、ui/benchmark_reference_review.py／static/benchmark-references.js、scripts/prepare-benchmark-references.py／ps1，新合同行为／原片页面／实际入口测试与公共记忆／指南。复用loads_plan／freeze_document的实际时长校验、既有publish_review_bundle的独占目录／最后回执及本地FFmpeg.probe；不新增HTTP／SQL，不修改既有冻结或候选评分算法。

支持中文／空格；输出保护原输入／源文件／原参考包／记录。引用hash固定原context，导入再核对实际源SHA／时长／原查询等不可变资料，允许编辑参考与人工元数据。源时钟非零或音视频起点不同暂禁播放器自动取时，手工规范源时间仍可填写；播放器位置非精确裁切，不能自动扩写可用区间。操作下载／载入不能覆盖新编辑或串查询；原数据与模型／费用保持。

验证：新空参考／用户多区间／边界与重复／来源和查询篡改／确认元数据／过大非有限值；生成／导入真实源文件校验与旧包只读；1366／390原片播放、标起止／手填区间、记录下载载入、错误保护与计划导出。使用开发片演示，不产生新真实人评。完成相关检查后再整体验证／离线包；不循环TD012旧保存问题，不越F006做正式编排／渲染／商业。

## 当前交付

### 真实流程与完整检查

root接af11042，本goal turn上一轮为progress：保存实现／通俗汇报／Git检查点。fresh工作树干净、init CheckOnly及完整隔离工具通过。公开PowerShell7已生成三开发源原片标注包，1366／390各三原录像实际播放／暂停及起止标记（特殊时钟禁自动）、程序示例下载重载；空记录与程序示例分别导出旧plan，空记录接原freeze成功。全部保留人工确认false／development与已看结果true，原Atom两片仍同组／两已知组／独立准备false／qualityGate null。

验证脚本先用CSP禁止的字符串谓词，再误认freeze的qualityGate层级，读回又误套review回执合同；均直接修验证方式、保留原输出，没有放宽产品或重做数据。之后复用严格read_freeze，两个进程核对原source SHA／页面包回执／两导出／原冻结均一致。耗时未及时落盘，不估算；第一次实验baseline未持久化，不称整个实验旧项目完整比对。**最终只读核对阶段858个旧项目文件**、原页面包／待授权proposal保持，三个源SHA与之前冻结相同。artifacts/benchmark-reference-review-validation/report.json／原stdout、stderr、失败说明、下载及截图留证；0本功能模型／上传／搜索／预留／真实人评。

三实际开发源均特殊时钟，自动取时禁用，六次实际播放使用手填起止；合成零起点自动取时仍由两浏览器合同验证，不移称真实特殊时钟验证。root已看双尺寸截图，布局清楚／无横溢。原片标注指南、README／用户手册／冻结与人工验收指南、架构／AGENTS命令及F006 evidence同步；旧用户手册“网页只能单任务”直接纠正，验收passes未改。

一次完整**2225passed／3旧批次准备失败／1权限skip，441.531s JUnit**，22新检查全部通过。失败为test_corrupt_batch_records_refuse_before_media_work[state.json]的storage.batch_checkpoint、test_coverage_is_reported_without_analysis_command_or_new_budget期望2实际5，以及原准备页刷新／停止流程disabled等待超时，原因未确认、TD012延期。窄复查首命令漏建basetemp父目录三setup错误无测试执行，原xml／log保留；正确准备目录后仅一次三项复查3passed6.121s（控制台6.19），不改生产／加重试／重跑整套。

170格式／lint、88文件mypy通过；整套失败后单独完成CLI和双离线wheel，SHA**ec298280844703b52715680ec6cdf15844d909f38145b32ddc8ba30796f5ad60**。87包文件逐字节等源码，无媒体／缓存／DB，另一个进程从wheel读静态资源并渲染，同一已读取context与源码HTML SHA相同。初次包验证误将canonical JSON重读后的字段顺序与首次构造字典渲染逐字节比，直接纠正验证预期，不改产品／包。源码与06771ee完全相同，本轮后续只有文档与ignored证据，无须重复静态／完整检查。

回执.cache/benchmark-reference-{final-tests.xml,final-verify.log,recheck.xml,recheck-final.xml,recheck-final.log,package.json,build.log,cli.log}；publicEntry／六原片播放／两下载重载／严格第二进程证据在ignored report。已通俗汇报当前可看原片登记并继续／导出原freeze，真实三源手填限制、旧失败只针对性复查和零模型费用；[正式汇报](report-2026-10-07-reference-review.md)。现用工作台无新路由或静态改动，不重启。

下一root仍Phase 0 F006：核对独立素材与事前查询／人工参考的真实前置资料，组织实际人评与固定原排名评测；不能把现有七文件／两已知组或程序示例当十独立会话，不代填确认、评分或越阶段。先登记下一可执行主要交付，旧worker和小问题冻结／延期。上一网络连接失败，本轮0push／远端读取，上次799625c、本地06771ee及后续文档待补推，保存以Git和.cache/benchmark-reference-publication.json为准，goal active。

### 额度14%检查点（历史）

2026-10-07用户请求汇报，保存未验收检查点；纯context／记录验证、本机HTML与JavaScript、多区间标注／下载重载、重验源身份后旧plan导出，以及Python／PowerShell入口已实现。新公开Python脚本已加入verify格式／lint和项目mypy文件表，root同时拥有这两处集成配置。无新HTTP／SQL／模型，现用工作台不重启、不增加新页面入口。

新合同行为20passed（.cache/benchmark-reference-core.xml）；首次19passed／1测试HTML转义断言失败保留first.xml，直接修正断言后通过，无产品凑数修改。1366／390两项原片浏览器流程2passed（.cache/benchmark-reference-browser.xml），实际生成2秒MP4：媒体读取／定位与起点抓取、同事件多个可用区间／查询切换、下载和载入、拒绝改事前声明以及异步载入不覆盖正在编辑内容。没有实际游戏人工标签，不能算独立验收或真实动作理解。集成配置变动后170文件格式／lint、88文件mypy与git diff --check通过，.cache/benchmark-reference-checkpoint-checks.log保存；不引用旧整套为本轮通过。

尚未运行本轮真实游戏录像公开PowerShell入口／实际播放／原冻结衔接／第二进程核对、完整verify与双wheel，指南和正式交付尚未完成。当前完整22项是20合同＋2页面，不宣称全量通过。源时钟特殊情况仍手工填写，不扩写区间或猜独立来源。

源码检查点06771ee已本地提交；一次普通push连接github.com:443在21.131秒后失败／exit128，原日志保留，不重试、不读取远端。上次独立确认799625c，本轮新检查点未远端同步，网络恢复后补推原授权分支；最终发布状态见.cache/benchmark-reference-checkpoint-publication.json。仅文档补事实不重跑源码检查。

阶段通俗结论及下一步见[额度14%汇报](report-2026-10-07-reference-checkpoint.md)。现用批量准备／联合搜索已交付；新原片标注正在验证。fresh只读健康确认8765／45524／28036与media-preparation-v1，未重启。0新模型／上传／普通搜索／费用预留／真实人评，旧unknown4.065536／待答新提案保持，F006/F009/F010false，旧worker冻结，goal active。

下一条具体操作：读取既有开发计划的三源路径，在新的ignored验证目录建立development／modelResultsViewed=true、人工确认false的原片标注包，通过项目隔离PowerShell7公开入口生成／导入空记录并交给旧freeze；验证实际源身份与旧项目／费用不变。再用1366／390核对实际原片播放、标区间与保存重载；程序演示标记不得当人工标签或独立测试。完成后一次整体验证／包核对、使用指南、提交交付；不循环TD012。保存／推送以Git和.cache/benchmark-reference-checkpoint-publication.json为准，普通授权工作分支，不改main／强推。
